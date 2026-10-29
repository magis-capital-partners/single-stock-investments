"""Preserve publisher bytes and forecast vintages in the private vault checkout."""
import argparse
from pathlib import Path
import shutil


def preserve(source,vault):
    destination=vault/'dashboard-private/commodity-inputs'
    if not (source/'observations.json').is_file():return 0
    destination.mkdir(parents=True,exist_ok=True)
    # Object names are content hashes, including CSV/HTML originals. Preserve
    # exact publisher bytes even when Git has Windows newline conversion on.
    (destination/'.gitattributes').write_text('objects/* binary\nforecast-vintages/*.xlsx binary\n',encoding='utf-8')
    shutil.copy2(source/'observations.json',destination/'observations.json')
    for folder in ['objects','vintages','forecast-vintages','free-vintages']:
        if (source/folder).is_dir():shutil.copytree(source/folder,destination/folder,dirs_exist_ok=True)
    return 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('_private/commodity'))
    parser.add_argument('--vault',type=Path,required=True)
    args=parser.parse_args();print('Commodity snapshot preserved:',preserve(args.source,args.vault))
