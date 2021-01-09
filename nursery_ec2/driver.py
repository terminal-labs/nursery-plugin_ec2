import ast
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from subprocess import PIPE
from subprocess import Popen

from bs4 import BeautifulSoup


def run_cmd(ep, cmd):
    return Popen([ep] + [*cmd], stdout=PIPE, stderr=PIPE).communicate()


class ec2Driver:
    """
    Handy Vagrant links:
        https://www.vagrantup.com/docs/other/environmental-variables.html
    """

    def __init__(self):
        """Find many facts about how VirtualBox and Vagrant are set up. For some things
        we need to discern what the source of truth is on a system. For vbox, we rely
        first on the what VBoxManage thinks, then fall back to other guesses.
        """
        self.vboxmanage_path = Path(shutil.which("VBoxManage"))
        self.vbox_version = self.vbox_cmd(["--version"])[0].decode().strip()
        self.vbox_system_properties = self.get_system_properties()

        if (config_dir := os.getenv("VBOX_USER_HOME")) :
            self.vbox_config_dir = config_dir
        elif os.name == "nt":
            self.vbox_config_dir = Path.home() / ".VirtualBox"
        elif sys.platform == "darwin":
            self.vbox_config_dir = Path.home() / "Library" / "VirtualBox"
        else:
            self.vbox_config_dir = Path.home() / ".config" / "VirtualBox"

        self.vbox_machines_folder = self.vbox_system_properties[
            "Default machine folder"
        ]
        if (sys_prop := self.vbox_system_properties.get("Default machine folder")) :
            self.vbox_machines_folder = Path(sys_prop)
        else:
            self.vbox_machines_folder = Path.cwd()

        self.vagrant_path = Path(shutil.which("vagrant"))
        if (env_var := os.getenv("VAGRANT_HOME")) :
            self.vagrant_home = Path(env_var)
        else:
            self.vagrant_home = Path.home() / ".vagrant.d"

        self.vagrant_boxes_path = self.vagrant_home / "boxes"

    def get_vbox_config(self):
        with open(self.vbox_config_dir / "VirtualBox.xml") as fp:
            config = fp.read()

        return BeautifulSoup(config, "lxml")

    def get_system_properties(self):
        raw = self.vbox_cmd(["list", "systemproperties"])[0].decode().splitlines()
        kvs = [line.split(":") for line in raw]
        system_properties = {}
        for k, v in kvs:
            system_properties[k] = v.strip()

        return system_properties

    def list_vms(self):
        vms = self.vbox_cmd(["list", "vms"])[0].decode().splitlines()
        return {vm.split('"')[1]: vm[-37:-1] for vm in vms}

    def show_vm_info(self, name_or_uuid):
        info = (
            self.vbox_cmd(["showvminfo", name_or_uuid, "--machinereadable"])[0]
            .decode()
            .splitlines()
        )

        rv = {}
        for line in info:
            k, v = line.split("=")
            try:
                k = ast.literal_eval(k)
            except ValueError:
                pass
            rv[k] = ast.literal_eval(v)

        return rv

    def import_ovf(self, name):
        ovf_path = self.ovf_path(name)

        # Doing dry-run import to determine parallel-safe name...
        ovf_data = self.ovf_data(name)
        vsys_data = self.virtual_system_data(ovf_data["virtual system"])

        name = vsys_data["Suggested VM name"]

        # Ensure we never have colliding names in case of parallel operations
        # by appending a timestamp and partial uuid to the suggested name
        name = f"{name}-{time.time()}-{str(uuid.uuid4())[:8]}"

        disk_args = []
        for disk in vsys_data["Hard disk image"]:
            image_file = disk.split("target path=")[1].split(",")[0]
            vsys_disk_unit = [
                unit
                for unit in ovf_data["virtual system"]
                if disk in ovf_data["virtual system"][unit]
            ][0]
            disk_args += [
                "--vsys",
                "0",
                "--unit",
                vsys_disk_unit,
                "--disk",
                self.vbox_machines_folder / name / image_file,
            ]

        import_cmd = ["import", ovf_path, "--vsys", "0", "--vmname", name, *disk_args]

        return import_cmd

    def ovf_data(self, name):

        raw = self.vbox_cmd(["import", "--dry-run", self.ovf_path(name)])[0].decode()
        raw = raw.splitlines()
        data = {}

        description_line = False

        for line in raw:
            # This loop handles an oddly formatted output line-by-line, based on the
            # lines that came before. Thus, there's many `continue`s as we pass expected
            # blocks of raw output.

            if line == "Disks:":
                parsing_disks = True
                data["disks"] = []
                continue

            if parsing_disks:
                if line:
                    data["disks"].append(line.split())
                    continue
                else:
                    parsing_disks = False
                    continue

            if "Virtual system" in line:
                # This loop expects only one virtual system associated with the ovf
                parsing_system = True
                data["virtual system"] = {}
                continue

            if parsing_system:
                line = line.strip()

                if line[0] == "(":
                    # Set and keep True until description line is terminated
                    description_line = True
                if description_line:
                    if line[-1] == ")":  # Line terminated. Unset flag.
                        description_line = False
                    continue

                try:
                    int(line.split(":")[0])  # e.g. line starts with " 7:"
                except ValueError:
                    new_data_line = False
                else:
                    new_data_line = True

                if new_data_line:
                    data_line = line
                else:
                    data_line = data_line + line

                key = data_line.split(":")[0]
                value = " ".join(data_line.split(":")[1:]).strip()
                data["virtual system"][key] = value

        return data

    def _variable_size_value(self, original, addition):
        """Return string or list of strings depending on previously value of
        original data.
        """
        if not original:
            return addition
        elif isinstance(original, str):
            return [original, addition]
        elif isinstance(original, list):
            return original.append(addition)

    def virtual_system_data(self, vsys):
        """Return a dict from a given unparsed "Virtual system" part of an import's
        command output. This is useful together with self.ovf_data.
        """
        rv = {}

        for line in vsys.values():
            if "Suggested OS type" in line:
                rv["Suggested OS type"] = line.split('"')[-2]
            elif "Suggested VM name" in line:
                rv["Suggested VM name"] = line.split('"')[-2]
            elif "Suggested VM group" in line:
                rv["Suggested VM group"] = line.split('"')[-2]
            elif "Suggested VM settings file name" in line:
                rv["Suggested VM settings file name"] = line.split('"')[-2]
            elif "Suggested VM base folder" in line:
                rv["Suggested VM base folder"] = line.split('"')[-2]
            elif "Product (ignored)" in line:
                rv["Product (ignored)"] = line.split("  ")[1]
            elif "Number of CPUs" in line:
                rv["Number of CPUs"] = line.split("  ")[1]
            elif "Guest memory" in line:
                rv["Guest memory"] = line.split("  ")[1]
            elif "Network adapter" in line:
                rv["Network adapter"] = line.split("  ")[1]
            elif "CD-ROM" == line:
                rv["CD-ROM"] = True
            elif "SCSI controller" in line:
                rv["SCSI controller"] = line.split(", ")[1]
            elif "IDE controller" in line:
                rv["IDE controller"] = self._variable_size_value(
                    rv.get("IDE controller"), line.split(", ")[1]
                )
            elif "Hard disk image" in line:
                rv["Hard disk image"] = self._variable_size_value(
                    rv.get("Hard disk image"), line.split("  ")[1]
                )
            else:
                print(f"Unhandled virtual system data line: {line}")

        return rv

    def ovf_path(self, name, box_version=None):
        if name in self.vagrant_boxes():
            if box_version:
                return (
                    self.vagrant_boxes_path
                    / name
                    / box_version
                    / "virtualbox"
                    / "box.ovf"
                )
            else:
                return (
                    self.vagrant_boxes_path
                    / name
                    / self.vagrant_boxes()[name][0]
                    / "virtualbox"
                    / "box.ovf"
                )

    def get_soup(self, path):
        """Generic helper to return bs4 soup of an xml file,
        such as .config/VirtualBox/VirtualBox.xml
        """
        with open(path) as fp:
            return BeautifulSoup(fp.read(), "lxml")

    def vagrant_boxes(self):
        return {n: self.vagrant_box_versions(n) for n in self.vagrant_box_names()}

    def vagrant_box_names(self):
        return [box.name for box in self.vagrant_boxes_path.iterdir() if box.is_dir()]

    def vagrant_box_versions(self, box_name):
        name_path = self.vagrant_boxes_path / box_name
        versions = [path.name for path in name_path.iterdir() if path.is_dir()]
        return sorted(versions, reverse=True)

    def vbox_cmd(self, cmd):
        return run_cmd(self.vboxmanage_path, cmd)
