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

import re
import sys
sys.setrecursionlimit(10000)

is_key = re.compile(
        r'''
        ^                       # beginning of a line
        ([\w\-]+)               # key, can be alpha and numbers, plus '-'
        \ +                     # any space
        \{                      # end by '{'
        $                       # end of a line
        ''', re.UNICODE | re.VERBOSE
)
is_double_key = re.compile(
        r'''
        ^                       # beginning of a line
        ([\w\-]+)               # 1st key, can be alpha and numbers, plus '-'
        \ +                     # any space
        ([\w\-\"\./@:=\+]+)     # 2nd key
        \ +                     # any space
        \{                      # end by '{'
        $                       # end of a line
        ''', re.UNICODE | re.VERBOSE
)

is_key_value = re.compile(
        r'''
        ^                       # beginning of a line
        ([\w\-]+)               # key
        \ +                     # any space
        ['"]?(.*?)['"]?$     # value may be inside of single or double quote
        ''', re.UNICODE | re.VERBOSE
)

is_flag = re.compile(
        r'''
        ^                       # beginning of a line
        ([\w\-]+)               # value
        ''', re.UNICODE | re.VERBOSE
)

is_comments = re.compile(
        r'''
        ^                       # beginning of a line
        (\/\*).*(\*\/)          # comments between /* and */
        ''', re.UNICODE | re.VERBOSE
)

"""
    A recursive function to traverse the vyatta configuration trees
    variables:
        - lines : list of source configuration in lines, 
        - node  : current node at the parsed configuration dictionary
        - tree  : single branch tree of the list of nodes
        - type  : another tree to handle double key items. 2 means double key
"""
def vyatta_parse_line(lines, node, tree, type):
    if not lines:
        return

    line = lines[0].strip()
    if line:
        if(line == "}"):
            # end of section, if current node is part of double key node,
            # we need to go up two nodes
            if(type[-1] == 2):
                tree.pop()
                type.pop()
            tree.pop()
            type.pop()
        else: 
            match = is_key.match(line)
            if match:
                key         = match.groups()[0]
                node[key]   = {}
                node        = node[key]
                tree.append(node)
                type.append(1)
            else:
                match = is_double_key.match(line)
                if match:
                    key         = match.groups()[0]
                    if key not in node:
                        # add a new node when key not found
                        node[key]= {}           

                    # go to next level
                    node    = node[key]         
                    tree.append(node)
                    # mark current level is a double key
                    type.append(2)

                    # add 2nd key as it must be unique
                    key         = match.groups()[1]
                    node[key]   = {}
                    node        = node[key]
                    tree.append(node)
                    type.append(2)                        
                else:
                    match = is_key_value.match(line)
                    if match:
                        key     = match.groups()[0]
                        value   = match.groups()[1]
                        if ( key in node ):
                            # duplicated key, such as "address xxx"
                            if isinstance(node[key], list):
                                node[key].append(value)
                            else:
                                # convert original item to list for multi-values
                                values = [node[key], value]
                                node[key] = values
                        else:
                            if value is None:
                                # denote empty string
                                node[key] = ""
                            else:
                                node[key] = value
                    else:
                        match = is_flag.match(line)
                        if match:
                            value       = match.groups()[0]
                            node[value] = ""

    lines.pop(0)
    vyatta_parse_line(lines, tree[-1], tree, type)

    return

"""
    Parse a vyatta configuration file in string format into configuration dictionary
"""
def vyatta_cfg_parser(s):
    s       = s.splitlines()
    config  = {}
    tree    = [config]
    type    = []
    vyatta_parse_line(s, config, tree, type)

    return config



