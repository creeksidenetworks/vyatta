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

import  os.path
from    tempfile import NamedTemporaryFile

import  re
import  json
import  sys
sys.setrecursionlimit(10000)

from    scp import SCPClient, SCPException
import  time
from    src.utilities import *

# pre-defined edgeos commands
router_cfg_cmd="/opt/vyatta/sbin/vyatta-cfg-cmd-wrapper"
router_run_cmd="/opt/vyatta/bin/vyatta-op-cmd-wrapper"
vyatta_api="/opt/vyatta/sbin/my_cli_shell_api"

class VyattaRouter(object):
    def __init__(self, ssh_client):
        # SSH client
        self.sshclient          = ssh_client
        self.cfg_session_open   = False
        self.codec              = "utf-8"
        self.info               = {}

    def run_os_command(self, command):
        """
        Run an linux os command
        :param command: vyatta operational command, str type
        :returns: command output
        """
        stdin, stdout, stderr = self.sshclient.exec_command(command)
        return stdout.read().decode(self.codec).rstrip("\n")

    def run_op_command(self, command):
        """
        Run an vyatta operational command
        :param command: vyatta operational command, str type
        :returns: command output
        """
        return self.run_os_command(f"/opt/vyatta/bin/vyatta-op-cmd-wrapper {command}")

    def cfg_in_session(self):
        """
        return True if a vyatta configure session is open
        """
        return (self.cfg_session_open)

    def cfg_start_session(self):
        """
        start a configuration session
        """        
        if not self.cfg_session_open:
            self.cfg_session = self.sshclient.invoke_shell(width=1024, height=10240)
            self.cfg_stdin   = self.cfg_session.makefile('wb')
            self.cfg_stdout  = self.cfg_session.makefile('rb')
            self.cfg_session_open = True
            self.cfg_send_command(f"configure", echo=False)
        else:    
            raise Exception ("Vyatta configure session was already opened")

    # send a configure command, and print response if required
    # return response
    def cfg_send_command(self, command, echo=True, timeout=300):
        if self.cfg_session_open:
            response = []
            # clean up previous buffer if any
            while self.cfg_session.recv_ready():
                self.cfg_session.recv(1024)
            
            self.cfg_session.send(f"{command}\n")
            buffer = ""
            first_line = True

            for timer in range (0, timeout*10, 1):
                while self.cfg_session.recv_ready():
                    buffer += str(self.cfg_session.recv(1024).decode(self.codec))

                lines = buffer.splitlines()
                len_lines = len(lines)
                if(len_lines > 1):
                    for i in range(0, len_lines):
                        # bypass empty lines
                        if(lines[i].strip() == ""):
                            continue
                        # find magic word, end of command
                        if ("[edit]" in lines[i]):
                            return response
                        response.append(lines[i])
                        if echo:
                            if first_line:
                                print(f"      o {lines[i]}")
                                first_line = False
                            else:
                                print(f"        {lines[i]}")
                
                    if(buffer.endswith("\n")):
                        buffer = ""
                    else:
                        # if last line is not received completely
                        buffer = lines[i]

                time.sleep(0.1)
            raise Exception("Time out") 
        else:    
            raise Exception ("Not in a vyatta configure session")

    # execute commit-confirm command
    # when finish, confirm the commit to avoid reboot
    # return response
    def cfg_commit_confirm(self, echo=True, confirm_timer=30, timeout=600):
        if self.cfg_session_open:
            response = []
            if(not self.cfg_vyatta_api_status("sessionChanged")):
                print ("\n  -- No change, return")
                # no changes 
                return False

            # clean up previous buffer if any
            while self.cfg_session.recv_ready():
                self.cfg_session.recv(1024)
            
            self.cfg_session.send(f"commit-confirm {confirm_timer}\n")
            buffer = ""

            for timer in range (0, timeout*10, 1):
                while self.cfg_session.recv_ready():
                    buffer += str(self.cfg_session.recv(1024).decode(self.codec))

                lines = buffer.splitlines()
                len_lines = len(lines)
                if(len_lines > 1):
                    for i in range(0, len_lines):
                        if ("[yes]" in lines[i] or 
                            "[confirm]" in lines[i]):
                            self.cfg_session.send(f"y\n")
                        elif ("[edit]" in lines[i]):
                            self.cfg_send_command(f"confirm", echo=False, timeout=300)
                            return response

                        response.append(lines[i])
                        if echo:
                            print(f"       {lines[i]}")

                        if ("No configuration changes to commit" in lines[i]):
                            return response

                    if(buffer.endswith("\n")):
                        buffer = ""
                    elif "[yes]" in lines[i]:
                        # no new line when [yes]
                        buffer = ""
                    else:
                        # if last line is not received completely
                        buffer = lines[i]

                time.sleep(0.1)
            raise Exception("Time out") 
        else:
            raise Exception ("Not in a vyatta configure session")

    # use vyatta api to return single or multi config value(s),
    # return string for single value or list for multi values
    # supported commands:
    #    > listNodes
    #    > returnValue(s)
    def cfg_vyatta_api_get(self, command, timeout=30):
        if self.cfg_session_open:
            # clean up previous buffer if any
            while self.cfg_session.recv_ready():
                self.cfg_session.recv(1024)
            
            first_command = command.split()[0]

            self.cfg_session.send(f"{vyatta_api} {command}\n")
            buffer = ""

            for timer in range (0, timeout*10, 1):
                while self.cfg_session.recv_ready():
                    buffer += str(self.cfg_session.recv(1024).decode(self.codec))

                if "[edit]" in buffer:
                    lines = buffer.splitlines()
                    for line in lines:
                        if line.endswith("[edit]"):
                            if (first_command.endswith("s")):
                                # get multiple value, return list
                                return line.split("[edit]", 1)[0].replace("'", "").split()
                            else:
                                # single value, return string
                                return line.split("[edit]", 1)[0]

                time.sleep(0.1)
            raise Exception("Time out") 
        else:
            raise Exception("*** Not in a configure session ***") 
    """
    * use vyatta api to check various status,
    * return boolean value (True or False)
    * supported commands:
        > exists (and extensions)
        > session status (Changed, Unsaved) 
    """
    def cfg_vyatta_api_status(self, command, timeout=30):
        if self.cfg_session_open:
            # clean up previous buffer if any
            while self.cfg_session.recv_ready():
                self.cfg_session.recv(1024)
            
            self.cfg_session.send(f"{vyatta_api} {command} && echo True || echo False\n")
            buffer = ""

            for timer in range (0, timeout*10, 1):
                while self.cfg_session.recv_ready():
                    buffer += str(self.cfg_session.recv(1024).decode(self.codec))

                if "[edit]" in buffer:
                    lines = buffer.splitlines()
                    for line in lines:
                        if (line == "True"):
                            return True
                        elif (line == "False"):
                            return False

                time.sleep(0.1)
            raise Exception("Time out") 
        else:
            raise Exception ("Not in a vyatta configure session")

    #close a confige session
    def cfg_close_session(self, timeout=30):
        if self.cfg_session_open:
            if(self.cfg_vyatta_api_status("sessionChanged")):
                # clean up previous buffer if any
                while self.cfg_session.recv_ready():
                    self.cfg_session.recv(1024)
            
                self.cfg_session.send(f"exit discard\n")
                buffer = ""

                for timer in range (0, timeout*10, 1):
                    while self.cfg_session.recv_ready():
                        buffer += str(self.cfg_session.recv(1024).decode(self.codec))

                    if "exit" in buffer:
                        lines = buffer.splitlines()
                        for line in lines:
                            if line.endswith("exit"):
                                self.cfg_session.close()
                                return True

                    time.sleep(0.1)
                raise Exception("Time out") 
            else:
                self.cfg_session.close()
                self.cfg_session_open = False
                return True
        else:
            raise Exception ("Not in a vyatta configure session")

    def cfg_save(self, path_config_file=""):
        self.cfg_send_command(f"save {path_config_file}", echo=False, timeout=300)

    """
    upload files to router
    if the destiantion is under /tmp, simply scp
    else, upload to tmp folder, then move it to destination to workaround permissions
    """
    def upload(self, local_path, remote_path):
        filename = remote_path.rsplit("/", 1)[1]
        # upload to temp folder to workaround permission issue
        if (remote_path[0:4] != "/tmp"):
            tmp_dir = self.run_os_command(f"mktemp -d")
            path_upload_file = f"{tmp_dir}/{filename}"
 
            with SCPClient(self.sshclient.get_transport()) as scp:
                scp.put(
                    local_path,
                    remote_path=path_upload_file,
                    recursive=False
                )

            target_dir = remote_path.rsplit("/", 1)[0]
            self.run_os_command(f"sudo mkdir -p {target_dir}")
            self.run_os_command(f"sudo mv -f {tmp_dir}/{filename} {remote_path}")
            self.run_os_command(f"sudo rm -rf {tmp_dir}")
        else:
            with SCPClient(self.sshclient.get_transport()) as scp:
                scp.put(
                    local_path,
                    remote_path=remote_path,
                    recursive=False
                )
        # make it executable if the uploaded file is a script
        if (remote_path.rsplit(".", 1)[1] == "sh"):
            self.run_os_command(f"sudo chmod +x {remote_path}")            

    """
    upload string to router as a file
    """
    def upload_str_as_file(self, file_as_string, remote_path):
        f = NamedTemporaryFile(delete=False)
        fname = f.name
        f.write(bytes(file_as_string, 'utf-8'))
        f.close()

        self.upload(fname, remote_path)

        # unlock the file, so it can be collected by os
        os.unlink(fname)
        assert not os.path.exists(fname)

    # download a file from router
    def download(self, remote_path,local_path):
        with SCPClient(self.sshclient.get_transport()) as scp:
            scp.get(
                remote_path,
                local_path=local_path,
                recursive=False
            )
  
    """
    scan available ethernet interfaces and find following infor
        * interface name
        * address
        * link status
        * description
        * is active? (current ssh interface)
    """
    def scan_interfaces(self):
        info = {}
        # find out the management interface ip
        data = self.run_os_command("netstat -nt | grep :22.**ESTABLISHED").splitlines()
        management_ip = data[0].split()[3]
        management_ip = management_ip.split(":")[0]

        interface = ""
        data = self.run_op_command("show interfaces").splitlines()
        for line in data:
            if (line[0:3] == "eth"):
                type = "ethernet"
            elif (line[0:6] == "switch"):
                type = "switch"
            elif (line[0:6] == "tunnel"):
                type = "tunnel"
            elif (line[0:3] == "vti"):
                type = "vti"
            elif (line[0:2] == "lo"):
                type = "loopback"
            elif (line[0:2] == "wg"):
                type = "wireguard"
            elif (line[0:5] == "pppoe"):
                type = "pppoe"
            elif (line[0:5] == "     "):
                pass
            else:
                continue

            if type not in info:
                info[type]={}

            field = line.split(maxsplit=4)

            if (len(field) > 1):
                interface = field[0]
                address = field[1]

                if interface not in info[type]:
                    # first occurance of interface
                    info[type][interface]={}
                    info[type][interface]["addresses"] = [address]
                    info[type][interface]["active"] = False
                    info[type][interface]["link"] = field[2]

                    if (len(field) >= 4):
                        info[type][interface]["description"] = field[3]
                    else:
                        info[type][interface]["description"] = ""
            else:
                address = field[0]
                info[type][interface]["addresses"].append(address)

            # check if the address matches ssh login address
            if (address.split("/")[0] == management_ip):
                info[type][interface]["active"] = True
                if (type == "pppoe"):
                    # need to find the base ethernet interface
                    base_if = self.run_os_command("sudo cat /etc/ppp/peers/pppoe0 | grep nic-").split("-")[1]
                    info["ethernet"][base_if]["active"] = True
        return info

    def get_ipsec_key(self):
        privatekey_status   = self.run_os_command("[ -f /config/ipsec.d/rsa-keys/localhost.key ] && echo 'True' || echo 'False'")
        pubkey_status       = self.run_os_command("[ -f /config/ipsec.d/rsa-keys/localhost.pub ] && echo 'True' || echo 'False'")

        if (privatekey_status != 'True' or pubkey_status != 'True'):
            self.run_os_command("sudo mkdir -p /config/ipsec.d/rsa-keys")
            self.run_os_command("sudo rm -f /config/ipsec.d/rsa-keys/localhost.*")
            self.run_op_command("generate vpn rsa-key | grep -o \"0sAw.*\" | sudo tee /config/ipsec.d/rsa-keys/localhost.pub")

        public_key = self.run_os_command("sudo cat /config/ipsec.d/rsa-keys/localhost.pub")
        private_key = self.run_os_command("sudo cat /config/ipsec.d/rsa-keys/localhost.key")

        return public_key, private_key

    # update configuration by block
    def cfg_bulk_update(self, cfg_blocks, force=True):
        """ reference config blocks
        {
        "PUBLIC_LOCAL #200": {
            "path": "firewall name PUBLIC_LOCAL rule 200",
            "cmds": [
                    "action accept",
                    "description 'allow ike/nat0t'",
                    "destination port 500,4500",
                    "log disable",
                    "protocol udp",
            ]
        }
        """
        for subj in cfg_blocks.keys():
            path = cfg_blocks[subj]["path"]
            if self.cfg_vyatta_api_status(f"existsActive {path}"):
                if force:
                    print_status(f"\n    > {path[0:45]}", "replace")
                    self.cfg_send_command(f"delete {path}")
                else:
                    print_status(f"\n    > {path[0:45]}", "exists")
                    print("      ---------------------------------------------")
                    self.cfg_send_command(f"show {path}")
                    print("      ---------------------------------------------")
                    if ask_confirm(">>> Overwrite?", default=True, strict=False):
                        self.cfg_send_command(f"delete {path}")
                    else:
                        continue
            else:
                print_status(f"\n    > {path[0:45]}", "add")

            for cfg_cmd in cfg_blocks[subj]["cmds"]:
                self.cfg_send_command(f"set {path} {cfg_cmd}")


    def cfg_loopback_addr(self, loopback_addr):
        blocks = {
            "loopback address": {
                "path" : "interfaces loopback lo address",
                "cmds" : [
                    f"{loopback_addr}"
                ]
            }
        }
        self.cfg_bulk_update(blocks)

    def cfg_hostname(self, hostname):
        blocks = {
            "host name": {
                "path" : "system host-name",
                "cmds" : [
                    f"{hostname}"
                ]
            }, 
            "login banner": {
                "path" : "system login banner",
                "cmds" : [
                    f"pre-login \"\"",
                    f"post-login \"\\nWelcome to {hostname}\\n   - Proudly managed by Creekside Networks LLC\\n\""
                ]                
            }

        }   
        self.cfg_bulk_update(blocks)     

    def cfg_timezone(self, time_zone):
        blocks = {
            "time zone": {
                "path" : "system time-zone",
                "cmds" : [
                    f"{time_zone}"
                ]
            }
        }
        self.cfg_bulk_update(blocks)

    def cfg_system_dns(self, name_servers):
        blocks = {
            "time zone": {
                "path" : "system name-server",
                "cmds" : name_servers
            }
        }
        self.cfg_bulk_update(blocks)


    # configure an interface to use dhcp
    def cfg_interface_address_dhcp(self, interface):
        match interface[0:3]:
            case "eth":
                type = "ethernet"
            case "swi":
                type = "switch"
            case _:
                error_message = f"unsupported interface type '{interface}'"
                print("..."+error_message)
                raise Exception (error_message)

        cfg_blocks = {
            f"interface {interface} dhcp": {
                "path" : f"interfaces {type} {interface} address",
                "cmds" : [
                    f"dhcp",
                ]
            }
        }
        VyattaRouter.cfg_bulk_update(self, cfg_blocks)

    # configure an interface to use dhcp
    def cfg_interface_address_static(self, interface, addresses, force=False):
        match interface[0:3]:
            case "eth":
                type = "ethernet"
            case "swi":
                type = "switch"
            case  "tun":
                type = "tunnel"
            case "vti":
                type = "vti"
            case _:
                if (interface ==  "lo"):
                    type = "loopback"
                else:
                    raise Exception (f"unsupported interface type '{interface}'")

        title = f"interface {interface} static-ip"
        cfg_blocks = {
            f"{title}": {
                "path" : f"interfaces {type} {interface} address",
                "cmds" : []
            }
        }
        for address in addresses:
            cfg_blocks[title]["cmds"].append(address)
        VyattaRouter.cfg_bulk_update(self, cfg_blocks, force=force)


    def cfg_static_route(self, subnet, next_hop):
        cfg_blocks = {
            f"static route {subnet}": {
                "path" : f"protocols static route {subnet}",
                "cmds" : [
                    f"next-hop {next_hop}",
                ]
            }
        }
        VyattaRouter.cfg_bulk_update(self, cfg_blocks, force=force)        

    def install_packages(self):
        from src.devices import device_options

        path_ubnt_packages = "resources/packages"
        model = self.info["system"]["model"]

        # create a workspace
        tmp_dir = self.run_os_command(f"mktemp -d")

        # install other packages        
        for package_name in device_options[model]["packages"].keys():
            filename_deb = device_options[model]["packages"][package_name]

            installed_version = self.run_os_command("dpkg-query --show --showformat='${Version}' "+f"{package_name} 2> /dev/null || echo 'none'")

            if (installed_version != "none"):
                print_status(f"    > {package_name}", installed_version)
                continue
            else:
                print(f"    > {package_name} [{filename_deb}]")

                print_status("      o upload to router")
                self.upload(f"{path_ubnt_packages}/{filename_deb}", f"{tmp_dir}/{filename_deb}")
                print("ok")

                print_status("      o Install")
                self.run_os_command(f"sudo dpkg -i {tmp_dir}/{filename_deb}")
                print("ok")
        
                # Move package to firstboot path to automatically install package after firmware update
                print_status(f"      o make '{package_name}' permanent")
                firstboot_dir='/config/data/firstboot/install-packages'
                self.run_os_command(f"sudo mkdir -p {firstboot_dir}")
                self.run_os_command(f"sudo mv {tmp_dir}/{filename_deb} {firstboot_dir}/filename_deb")
                print("ok")

        # clean up workspace
        self.run_os_command(f"sudo rm -rf {tmp_dir}")

    # default zone policy, only PUBLIC and LOCAL zones are defined
    def cfg_zone_policy_local(self):
        cfg_blocks = {
            f"zone LOCAL": {
                "path" : f"zone-policy zone LOCAL",
                "cmds" : [
                    f"default-action 'drop'",
                    f"local-zone"
                ]
            }
        }
 
        VyattaRouter.cfg_bulk_update(self, cfg_blocks, force=True)

    def cfg_zone_policy_zone(self, new_zone, interface, local_policy="DEFAULT_ACCEPT", default_policy= "DEFAULT_DROP"):
        # search all existing zones, 
        # delete the interface settings in other zone
        # to avoid conflicts
        existing_zones = self.cfg_vyatta_api_get("listActiveNodes zone-policy zone")

        if new_zone in existing_zones:
            err = f"zone {zone} already exists"
            raise Exception(err)

        title = f"add zone {new_zone}"
        cfg_blocks = {
            f"{title}": {
                "path" : f"zone-policy",
                "cmds" : [
                    f"zone {new_zone} default-action 'drop'",
                    f"zone {new_zone} interface {interface}",
                ]
            }
        }

        for zone in existing_zones:
            # add policy for new zone
            if (zone == "LOCAL"):
                cfg_blocks[title]["cmds"].append(f"zone {new_zone} from LOCAL firewall name DEFAULT_ACCEPT")
                cfg_blocks[title]["cmds"].append(f"zone LOCAL from {new_zone} firewall name {local_policy}")
            else:
                cfg_blocks[title]["cmds"].append(f"zone {new_zone} from {zone} firewall name {default_policy}")
                cfg_blocks[title]["cmds"].append(f"zone {zone} from {new_zone} firewall name {default_policy}")

        VyattaRouter.cfg_bulk_update(self, cfg_blocks, force=True)

    def cfg_zone_policy_interface(self, zone, interface):
        # search all existing zones, 
        # delete the interface settings in other zone
        # to avoid conflicts
        zones = self.cfg_vyatta_api_get("listActiveNodes zone-policy zone")
        for this in zones:
            if (this != zone and
                self.cfg_vyatta_api_status(f"existsActive zone-policy zone {this} interface {interface}")):
                self.cfg_send_command(f"delete zone-policy zone {this} interface {interface}")

        title = f"add {interface} to zone {zone}"
        cfg_blocks = {
            f"zone {zone}": {
                "path" : f"zone-policy zone {zone} interface",
                "cmds" : [
                    f"{interface}",
                ]
            }
        }              
        VyattaRouter.cfg_bulk_update(self, cfg_blocks, force=True)

    # read config file from router
    def load_config(self, active=True):
        from src.vyatta_parser import vyatta_parse_config

        if active:
            s = self.run_os_command(f"/opt/vyatta/sbin/my_cli_shell_api showConfig --show-active-only")
        else:
            s = self.run_os_command(f"sudo cat /config/config.boot")

        config = vyatta_parse_config(s)

        return config

