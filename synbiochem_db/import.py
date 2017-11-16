'''
SYNBIOCHEM-DB (c) University of Manchester 2017

SYNBIOCHEM-DB is licensed under the MIT License.

To view a copy of this license, visit <http://opensource.org/licenses/MIT/>.

@author:  neilswainston
'''
# pylint: disable=invalid-name
import sys

from gg_utils.neo4j import utils
import pandas as pd


def import_metadata(filename):
    '''Import metadata.'''
    values = {}

    with open(filename, 'rU') as fle:
        in_options = False

        for line in fle:
            tokens = [val for val in line.strip().split(',') if val]

            if len(tokens) > 1:
                if 'Experimentalists List' in tokens:
                    in_options = True

                if in_options:
                    continue
                else:
                    values[tokens[0]] = tokens[1]

    df = pd.DataFrame(values, index=[0])
    df.to_csv('metadata.csv', index=False)
    return df


def parse_metadata(df):
    '''Parse metadata.'''
    rels = []

    # Get Experiment:
    exp_df = pd.DataFrame(df['Experiment Name/Revision'].values,
                          columns=['exp_id:ID'])
    exp_df[':LABEL'] = 'Experiment'

    # Get Person:
    person_df = pd.DataFrame(df['Experimentalist'].values,
                             columns=['name:ID'])
    person_df[':LABEL'] = 'Person'

    # Get Plate:
    plate_df = pd.DataFrame(df[['Analysis Plate Dilution Factor',
                                'Date Created (yymmdd)',
                                'Induction time',
                                'Lab Archives URL',
                                'Number of Well Plates',
                                'Plate ID (yymmdd-inst-exp)',
                                'Technology Type (e.g. GCMS)',
                                'Temperature']].values,
                            columns=['dilution_factor',
                                     'date_created',
                                     'induction_time',
                                     'lab_archives_url',
                                     'num_well_plates:int',
                                     'plate_id:ID',
                                     'instrument',
                                     'temperature:float'])
    plate_df[':LABEL'] = 'Plate'

    # Get Chemical:
    chem_df = pd.DataFrame(df.filter(regex='Target').transpose())
    chem_df.columns = ['chebi_id:ID']
    chem_df[':LABEL'] = 'Chemical'

    # Get Relationships:
    rels.append(df[['Plate ID (yymmdd-inst-exp)',
                    'Experiment Name/Revision']].values[0].tolist() +
                ['PART_OF'])

    rels.append(df[['Plate ID (yymmdd-inst-exp)',
                    'Experimentalist']].values[0].tolist() +
                ['CREATED_BY'])

    for chebi_id in chem_df['chebi_id:ID']:
        rels.append(df[['Plate ID (yymmdd-inst-exp)']].values[0].tolist() +
                    [chebi_id, 'HAS_TARGET'])

    rels_df = pd.DataFrame.from_records(rels, columns=[':START_ID', ':END_ID',
                                                       ':TYPE'])

    plate_id = df[['Plate ID (yymmdd-inst-exp)']].values[0][0]
    return [exp_df, person_df, plate_df, chem_df], [rels_df], plate_id


def import_strain(filename):
    '''Import strain.'''
    df = pd.read_csv(filename, usecols=range(13))[:8]
    df.set_index('PLATE #1', inplace=True)
    df.to_csv('strain.csv')
    return df


def parse_strain(df, plate_id):
    '''Parse strain.'''
    samples = [zip(df.index.values,
                   [col for _ in range(len(df.index))],
                   df[col].values)
               for col in df.columns]

    replicate_df = pd.DataFrame([pos for col in samples for pos in col],
                                columns=['loc_row', 'loc_col', 'rep_id'])

    replicate_df.dropna(how='any', inplace=True)
    replicate_df[':LABEL'] = 'Replicate'
    replicate_df['loc_well:ID'] = \
        replicate_df['loc_row'] + replicate_df['loc_col']

    replicate_rels_df = pd.DataFrame(
        replicate_df['loc_well:ID'], columns=['loc_well:ID'])
    replicate_rels_df.columns = [':END_ID']
    replicate_rels_df[':START_ID'] = plate_id
    replicate_rels_df[':TYPE'] = 'CONTAINS'

    sample_df = pd.DataFrame(columns=['host', 'plasmid', 'replicate'])
    sample_df[sample_df.columns] = \
        replicate_df['rep_id'].str.split('_', expand=True)
    sample_df['loc_well:ID'] = replicate_df['loc_well:ID']
    sample_df.drop('replicate', axis=1, inplace=True)

    host_df = pd.DataFrame(sample_df['host'], columns=['host'])
    host_df.columns = ['host_id:ID']
    host_df.drop_duplicates(inplace=True)
    host_df[':LABEL'] = 'Host'

    plasmid_df = pd.DataFrame(sample_df['plasmid'], columns=['plasmid'])
    plasmid_df.columns = ['plasmid_id:ID']
    plasmid_df.drop_duplicates(inplace=True)
    plasmid_df[':LABEL'] = 'Plasmid'

    host_rels_df = pd.DataFrame(sample_df[['host', 'loc_well:ID']],
                                columns=['host', 'loc_well:ID'])
    host_rels_df.columns = [':START_ID', ':END_ID']
    host_rels_df[':TYPE'] = 'FOUND_IN'

    plasmid_rels_df = pd.DataFrame(sample_df[['plasmid', 'loc_well:ID']],
                                   columns=['plasmid', 'loc_well:ID'])
    plasmid_rels_df.columns = [':START_ID', ':END_ID']
    plasmid_rels_df[':TYPE'] = 'FOUND_IN'

    return [replicate_df, host_df, plasmid_df], \
        [replicate_rels_df, host_rels_df, plasmid_rels_df]


def _get_filenames(dfs, prefix):
    '''Get filenames from DataFrames.'''
    filenames = []

    for idx, node_df in enumerate(dfs):
        filename = prefix + str(idx) + '.csv'
        node_df.to_csv(filename, index=False)
        filenames.append(filename)

    return filenames


def main(args):
    '''main method.'''
    metadata_df = import_metadata(args[0])
    node_dfs, rels_dfs, plate_id = parse_metadata(metadata_df)

    strain_df = import_strain(args[1])
    st_node_dfs, st_rels_dfs = parse_strain(strain_df, plate_id)

    node_dfs.extend(st_node_dfs)
    rels_dfs.extend(st_rels_dfs)

    node_files = _get_filenames(node_dfs, 'node')
    rels_files = _get_filenames(rels_dfs, 'rels')

    utils.create_db(args[2], node_files, rels_files)


if __name__ == '__main__':
    main(sys.argv[1:])