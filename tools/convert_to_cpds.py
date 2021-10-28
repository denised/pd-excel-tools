"""Convert one or more scenarios of a solution to custom pds representation.

Not all scenario adoptions can be well matched to the Excel code, owing to customization of the
Excel or to bugs in the Excel and/or the python code.  One alternative is to convert them to custom PDS
form, where we simply store the results as calculated in HelperTables into the scenario.
This utility does that conversion.  This utility replaces scenarios *in place*, so test it out with
backup in place."""

import json
from pathlib import Path
import pandas as pd
import numpy as np
import zipfile

from model import dd
from tools import util
from tools import solution_xls_extract as sxe

def _update_directory(datadirectory, entry):
    """Add the entry to the datadirectory if it is a new one, or update the existing one if not."""
    # This way if you execute this script multiple times for the same solution, you don't end up growing the directory ad infinitum
    for i in range(len(datadirectory)):
        if datadirectory[i]['name'] == entry['name']:
            datadirectory[i] = entry
            return
    datadirectory.append(entry)

def convert_to_cpds(solution, scenarios_to_convert, root=None):
    """Convert the names scenarios into custom pds adoption form, using the values found in expected.zip.
    Root, if provided is the path to the root directory of the solutions; by default the path relative to this script is used."""
    if root is None:
        root = Path(__file__).parents[1]/"solution"
    root = Path(root)

    solutiondir = root/solution
    if not solutiondir.is_dir():
        raise ValueError(f"Solution {solution} not found")
    
    expectedfile = solutiondir/"tests/expected.zip"
    if not expectedfile.is_file():
        raise ValueError(f"Expected.zip file not found in {solution}/tests")

    convert_all = not scenarios_to_convert

    datadir = solutiondir/"ca_pds_data"
    datadir.mkdir(exist_ok=True)
    datadirectoryfile = datadir/"ca_pds_sources.json"
    if datadirectoryfile.is_file():
        datadirectory = json.loads(datadirectoryfile.read_text(encoding='utf-8'))
    else:
        datadirectory = {}
    
    with zipfile.ZipFile(expectedfile) as zf:
        for acfile in solutiondir.glob('ac/*'):
            ac = json.loads(acfile.read_text(encoding='utf-8'))

            if convert_all or ac['name'] in scenarios_to_convert:
                print(f"Converting {ac['name']}...")
                helpertabletab = zf.open(ac['name'] + "/" + 'Helper Tables')

                helperdata = pd.read_csv(helpertabletab, header=None)
                effectiveadoption = util.df_excel_range(helperdata,"B91:L137")
                effectiveadoption.columns = pd.Index(['Year'] + dd.REGIONS)
                effectiveadoption.set_index('Year',inplace=True)

                # Convert columns that are all zeros to NaN's
                lastindex = effectiveadoption.last_valid_index()
                for r in dd.REGIONS:
                    if effectiveadoption[r].eq(0).all():
                        effectiveadoption[r] = np.NaN
                    else:
                        # check to see if this is an adoption that starts non-zero but then goes to zero
                        # this is a problematic case, since we can't be sure whether the trailing zeros
                        # should be zero, or should be NaN (this has been the source of errors in the past.)
                        # So we'll inform the user, and let them figure out what to do.
                        col = effectiveadoption[r]
                        lastnonzeroindex = col[col!=0].index[-1]
                        if lastnonzeroindex < lastindex:
                            print(f"Warning: scenario {ac['name']}, region {r}: adoption goes to zero or NaN, not sure which.\nWriting as NaN, correct manually.")
                            effectiveadoption.loc[lastnonzeroindex+1:,r] = np.NaN

                # name for this new adoption
                adoption_name = ac['name'] + '_ca'

                # output adoption data and update directory
                adoption_filename = datadir / sxe.get_filename_for_source(adoption_name)
                effectiveadoption.to_csv(adoption_filename)
                _update_directory(datadirectory, {
                    "name": adoption_name,
                    "include": True,
                    "description": "Autogenerated from original Excel adoption data for this scenario.",
                    "filename": adoption_filename.name
                })
                print(f"... {adoption_name} written.")

                # now we have to fix up this scenario to use this data, and make sure none of the things
                # that would mess with it are set
                ac["soln_pds_adoption_basis"]= "Fully Customized PDS"
                ac["soln_pds_adoption_custom_name"] = adoption_name
                ac["soln_pds_adoption_regional_data"] = False
                ac["pds_adoption_use_ref_years"] = []

                acfile.write_text(json.dumps(ac,indent=4), encoding='utf-8')
    
    datadirectoryfile.write_text(json.dumps(datadirectory, indent=4), encoding='utf-8')
    print("\nScenarios saved and data directory updated.")
    print("You may need to update the __init__.py file and you will need to add adoptions to skipped tests.")

                

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert named scenarios to Custom PDS Adoption form.')
    parser.add_argument('solution', help="Solution to convert")
    parser.add_argument('scenarios', nargs='*', help='Scenarios to search (names must match exactly).  If not provided, all scenarios will be converted.')
    parser.add_argument('--root', default=None, help="Where to find the solution directory, if not relative to __path__")
    args = parser.parse_args()

    convert_to_cpds(args.solution, args.scenarios, root=args.root)


