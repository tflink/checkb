#!/usr/bin/python3

from checkb.check import CheckDetail, export_YAML, import_YAML
import argparse
import os


def get_argparser():
    parser = argparse.ArgumentParser(description="This tool serves a purpose of generating "
                                                 "results from within a bash script. Results are "
                                                 "stored into output file in ResultsYAML format. "
                                                 "Each consecutive run of this tool will append "
                                                 "new results to specified file.")

    parser.add_argument("-f", "--file", help="output file", required=True)
    parser.add_argument("-i", "--item", help="item to be checked", required=True)
    parser.add_argument("-t", "--report_type", help="type of --item", required=True)
    parser.add_argument("-o", "--outcome", help="final outcome of check", required=True)
    parser.add_argument("-n", "--note", help="a few words or one-sentence note about the result",
                        default="")
    parser.add_argument("-k", "--keyval", action="append", default=[], metavar='KEY=VALUE',
                        help="all key-value pairs in this dictionary are stored "
                             "in ResultsDB as 'extra data'")
    parser.add_argument("-c", "--checkname",
                        help="name of the check (don't include namespace here)", default=None)
    parser.add_argument("-a", "--artifact", help="file or directory placed in the artifacts dir",
                        default=None)

    return parser


def main():

    parser = get_argparser()

    args = vars(parser.parse_args())

    output_file = args.pop('file')

    # parse additional key=value pairs
    keyvals = {}
    for var in args['keyval']:
        key, value = var.split('=', 1)
        keyvals[key] = value
    args['keyvals'] = keyvals
    args.pop('keyval')

    detail = CheckDetail(**args)

    if os.path.isfile(output_file):
        # if output file exists, parse its content and append new detail to it
        f = open(output_file, 'r+')
        yaml = f.read()
        details = import_YAML(yaml) if yaml else []
        details.append(detail)
        f.seek(0)
        f.write(export_YAML(details))
        f.close()
    else:
        # if output file doesn't exist, create it
        f = open(output_file, 'w')
        f.write(export_YAML([detail]))
        f.close()


if __name__ == "__main__":
    main()
