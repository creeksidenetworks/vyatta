#!/Users/jtong/python3/bin/python
# Edgerouter/VyOS management scripts
# Copyright (c) 2023 Jackson Tong, Creekside Networks LLC.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import  json
from    vyatta_parser import vyatta_cfg_parser
from    vyatta_differ import vyatta_cfg_differ

def test():
    ### testing for vyatta configure parser

    with open("data/config.active", "r") as f:
        s = f.read()
        f.close()
        active_config = vyatta_cfg_parser(s)

    print_summary(active_config, title = "Active")

    with open("data/config.working", "r") as f:
        s = f.read()
        f.close()
        working_config = vyatta_cfg_parser(s)

    print_summary(working_config, title = "working")

    # generate the delete lists for the active configs not exist in working version.
    deletes = vyatta_cfg_differ(working_config, active_config, partial=True)
    for cmd in deletes:
        print("delete " + " ".join(cmd))

    # generate the set lists for new/update configs.
    sets = vyatta_cfg_differ(active_config, working_config)

    for cmd in sets:
        print("set " + " ".join(cmd))

def print_summary(options, title="summary", indent = 4):
    summary = json.dumps(options, sort_keys=True, indent=4)
    indent_spaces = ' '*indent
    print()
    print(indent_spaces + "------------------------------------------------------------")
    print(indent_spaces + title)
    print(indent_spaces + "------------------------------------------------------------")
    for line in summary.splitlines():
        print(indent_spaces + line)
    print(indent_spaces + "------------------------------------------------------------")


if __name__ == '__main__':
    test()
