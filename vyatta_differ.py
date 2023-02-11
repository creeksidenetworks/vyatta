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

import sys
sys.setrecursionlimit(10000)

"""
generator:  vyatta_cfg_walker
            walk through configuration dict, and flat it to a list of lists.

"""
def vyatta_cfg_walker(node, tree=None):
    tree = tree[:] if tree else []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, dict):
                for d in vyatta_cfg_walker(value, tree + [key]):
                    yield d
            elif isinstance(value, list):
                for v in value:
                    for d in vyatta_cfg_walker(v, tree + [key]):
                        yield d
            else:
                if (value == ""):
                    yield tree + [key, "\"\""]
                else:
                    yield tree + [key, f"\"{value}\""]
    else:
        # multi-value entries, such as "address x.x.x.x/x"
        yield tree + [f"\"{node}\""]


"""
generator:  vyatta_cfg_differ
            compare two config sets, and generate the differnce.
input   :   
            active/working:     two configuration sets in dictionary
                                to generate "delete" command, swap active and working sets,
            partial:            if True, it will dive into leaf, return full path of changes, used for "set" command
                                if False, it will stop at the first branch, used for "delete" command
return  :   
            iterator object, a list of lists, for configuration paths, such as 
            [
                ["firewall", "group"].
                ["interfaces", "ethernet", "eth0", "address", "dhcp"]
            ]
"""
def vyatta_cfg_differ(active, working, partial=False, tree=None):
    tree = tree[:] if tree else []
    
    if isinstance(working, dict):
        for key, value in working.items():
            if key not in active:
                if partial:
                   yield tree + [key]
                else: 
                    for d in vyatta_cfg_walker(working[key]):
                        yield tree + [key] + d
            elif isinstance(value, dict):
                # go to next level
                for d in vyatta_cfg_differ(active[key], value, partial, tree + [key]):
                    yield d
            else:
                # convert list or value to sets for further comparison
                active_v  = set(active[key]) if isinstance(active[key], list) else set([active[key]])
                working_v = set(value) if isinstance(value, list) else set([value])
 
                for diff in working_v.difference(active_v):
                    yield tree + [key, f"\"{diff}\""]
    elif (active != working):
        yield tree + [f"\"{working}\""]
