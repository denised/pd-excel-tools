"""Template for extracting data from the expected csv's back into scenario json.
"""
import glob
import os
import json
import pandas as pd
import zipfile
import importlib

# Note that this timestamp could be one second off from the original Excel because our exported 
# float precision is a bit too low. We export floats like
# 43782.55755787 whereas one second in days = 1/86400 = 
#      .000011574074074074073...
# so rounding errors can occur. 
def from_excel_timestamp(days_float, _epoch0=datetime.datetime(1899, 12, 31)):
    if days_float >= 60:
        days_float -= 1  # Excel leap year bug, 1900 is not a leap year!
    return (_epoch0 + datetime.timedelta(days=days_float)).replace(microsecond=0)

def find_scenario_in_record(df_expected, scenario_name):
    """Find scenario start via 'Name of Scenario' row (or None if not found)."""
    name_header_col = df_expected[:][3]
    names_col = df_expected[:][4]
    scenario_start_row = None
    for row_idx, val in enumerate(name_header_col):
        if val == 'Name of Scenario:' and names_col[row_idx] == scenario_name:
            scenario_start_row = row_idx
            break
    return scenario_start_row

def all_solutions(solution_basedir):
    """Return all solutions with a solution/ subdir."""
    solution_pys = glob.glob(os.path.join(solution_basedir, '*', '__init__.py'))
    solutions = []
    for solution_py in solution_pys:
        solution_dirname = os.path.dirname(solution_py)
        solutions.append(os.path.split(solution_dirname)[-1])
    return sorted(solutions)


def copy_expected_to_ac_json(solution_basedir, solution_name):
    solution_dir = os.path.join(solution_basedir, solution_name)
    expected_filename = os.path.join(solution_dir, 'tests', 'expected.zip')
    ac_json_glob = os.path.join(solution_dir, 'ac', '*.json')
    ac_jsons = glob.glob(ac_json_glob)
    with zipfile.ZipFile(expected_filename) as zf:
        for ac_json in ac_jsons:
            print(ac_json)
            jsonfile = Path(ac_json).resolve()
            d = json.loads( jsonfile.read_text(encoding='utf-8') )
            scenario_name = d['name']

            # Read exported tab for the scenario from expected.zip. Note that the ScenarioRecord tab is especially
            # confusing: there's a separate exported file for each scenario, and each one holds _all_ the scenarios.
            sr_file = zf.open(scenario_name + "/" + 'ScenarioRecord')
            df_expected = pd.read_csv(sr_file, header=None, na_values=['#REF!', '#DIV/0!', '#VALUE!', '(N/A)'])

            scenario_start_row = find_scenario_in_record(df_expected, scenario_name)
            assert scenario_start_row is not None, f'Could not find rows for scenario {scenario_name} in {sr_file}'

            # Actually extract the datapoint we want and update the json dict.
            # Creation date could be a date string or an excel float, handle both.
            date_format = "%Y-%m-%d %H:%M:%S"
            creation_date_str = df_expected.iloc[scenario_start_row,1]
            if ':' in creation_date_str and '-' in creation_date_str:
                creation_date = datetime.datetime.strptime(creation_date_str, date_format)
            else:
                creation_date_float = float(creation_date_str)
                creation_date = from_excel_timestamp(creation_date_float)
            d['creation_date'] = creation_date.strftime(date_format)
            
            # Rewrite the json.            
            sxe.write_scenario(jsonfile, d)
    return ac_jsons

# Run over all solutions. 
solution_basedir = f'/Users/jpalex/dd/solutions/solution'  # Modify this as needed.
all_jsons_modified = []
for solution_name in all_solutions(solution_basedir):
    if solution_name == 'hfc_replacement':
        # subdir PDS2-82p2050-Median\ has a space at the end.
        continue
    all_jsons_modified.extend(copy_expected_to_ac_json(solution_basedir, solution_name))
print('Rewrote', len(all_jsons_modified), 'json files.')
