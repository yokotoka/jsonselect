#!/usr/bin/python

import argparse
import glob
import os
import os.path
import json
from jsonselect import select


def get_ctests(test_path):
    inputs = {}
    for selector_path in glob.iglob(os.path.join(test_path, '*.selector')):
        selector_file = os.path.basename(selector_path)
        root, ext = os.path.splitext(selector_file)
        prefix = root.split('_')[0]

        input_file = "%s%sjson" % (prefix, os.extsep)
        input_path = os.path.join(test_path, input_file)
        output_file = "%s%soutput" % (root, os.extsep)
        output_path = os.path.join(test_path, output_file)

        """
        print input_path
        print output_path
        print selector_path
        """

        if input_path not in inputs:
            with open(input_path) as f:
                inputs[input_path] = json.load(f)

        with open(selector_path) as selector_f:
            with open(output_path) as output_f:
                yield (selector_f.read().strip(),
                       inputs[input_path],
                       output_f.read().strip())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run JsonSelect conformance tests')
    parser.add_argument('--test', action='append', type=int, dest='tests',
                        choices=[1,2,3], help='Run this test')
    parser.add_argument('--verbose', action='store_true',
                       help='Print failed tests')

    args = parser.parse_args()
    tests = args.tests if args.tests else [1, 2, 3]

    for level in ('level_%s' % level for level in tests):
        test_failures = []
        total_tests = 0
        test_path = os.path.join('conformance_tests', level)
        print "Running tests in %s" % test_path

        for (selector, input, output) in get_ctests(test_path):
            total_tests += 1
            selection = select(selector, input)
            print "res: %s" % selection
            print "cmp: %s" % output
            if json.dumps(selection) != output:
                test_failures.append(selector)

        if len(test_failures):
            print "%s failed (%s/%s)" % (level, len(test_failures), total_tests)
            if args.verbose:
                for failure in test_failures:
                    print '\t%s' % failure
