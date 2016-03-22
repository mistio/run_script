#!/usr/bin/env python2
"""Run executable or ansible playbook on localhost

This takes care of fetching the script, unpacking it if it is a tarball or
zip file and actually executing the script. If the script is an ansible
playbook, then it bootstraps a python virtualenv where it installs ansible.

Only system wide requirement is a python2 interpreter >= 2.4.

"""

import os
import sys
import glob
import copy
import random
import urllib
import logging
import tarfile
import zipfile
import tempfile
import subprocess


# these settings affect ansible playbooks
PYPI_URL = "https://pypi.python.org/packages/source"
VENV_VERSION = "1.11.6"
ANSIBLE_VERSION = "1.7.2"


log = logging.getLogger(__name__)


def shellcmd(cmd, break_on_error=True):
    """Run a command using the shell"""
    log.debug("Running command '%s'.", cmd)
    return_code = subprocess.call(cmd, shell=True)
    if return_code:
        err = "Command '%s' exited with return code %d." % (cmd, return_code)
        if break_on_error:
            raise Exception(err)
        else:
            log.error(err)
    return return_code


def download(url, path=None):
    """Download a file over HTTP"""
    log.debug("Downloading %s.", url)
    name, headers = urllib.urlretrieve(url, path)
    log.debug("Downloaded to %s.", name)
    return name


def unpack(path, dirname='.'):
    """Unpack a tar or zip archive"""
    if tarfile.is_tarfile(path):
        log.debug("Unpacking '%s' tarball in directory '%s'.", path, dirname)
        tfile = tarfile.open(path)
        if hasattr(tfile, 'extractall'):
            tfile.extractall(dirname)
        else:
            for tarinfo in tfile:
                if tarinfo.isdir():
                    tarinfo = copy.copy(tarinfo)
                    tarinfo.mode = 0700
                tfile.extract(tarinfo, dirname)
    elif zipfile.is_zipfile(path):
        log.debug("Unpacking '%s' zip archive in directory '%s'.",
                  path, dirname)
        zfile = zipfile.ZipFile(path)
        if hasattr(zfile, 'extractall'):
            zfile.extractall(dirname)
        else:
            for member_path in zfile.namelist():
                dirname, filename = os.path.split(member_path)
                if dirname and not os.path.exists(dirname):
                    os.makedirs(dirname)
                zfile.extract(member_path, dirname)
    else:
        raise Exception("File '%s' is not a valid tar or zip archive." % path)

def find_folder(dirname='.'):
    """Find absolute path of script"""
    dirname = os.path.abspath(dirname)
    if not os.path.isdir(dirname):
        log.warning("Directory '%s' doesn't exist, will search in '%s'.",
                    dirname, os.getcwd())
        dirname = os.getcwd()
    ldir = os.listdir(dirname)
    if not ldir:
        raise Exception("Directory '%s' is empty." % dirname)
    if len(ldir) == 1:
        path = os.path.join(dirname, ldir[0])
        if os.path.isdir(path):
            dirname = path
            return path
    else:
        raise Exception("No folder found")

def find_path(dirname='.', filename=''):
    """Find absolute path of script"""
    dirname = os.path.abspath(dirname)
    if not os.path.isdir(dirname):
        log.warning("Directory '%s' doesn't exist, will search in '%s'.",
                    dirname, os.getcwd())
        dirname = os.getcwd()
    while True:
        log.debug("Searching for entrypoint '%s' in directory '%s'.",
                  filename or 'main.*', dirname)
        ldir = os.listdir(dirname)
        if not ldir:
            raise Exception("Directory '%s' is empty." % dirname)
        if len(ldir) == 1:
            path = os.path.join(dirname, ldir[0])
            if os.path.isdir(path):
                dirname = path
                continue
            break
        if filename:
            path = os.path.join(dirname, filename)
            if os.path.isfile(path):
                break
        paths = glob.glob(os.path.join(dirname, 'main.*'))
        if not paths:
            raise Exception("No files match 'main.*' in '%s'." % dirname)
        if len(paths) > 1:
            log.warning("Multiple files match 'main.*' in '%s'.", dirname)
        path = paths[0]
        break
    log.info("Found entrypoint '%s'.", path)
    return path


def bootstrap_venv(venv='./venv'):
    """Create a python virtualenv"""
    log.info("Bootstrapping python virtualenv.")

    log.info("Fetching virtualenv tarball.")
    venv_tarball_path = download("%s/v/virtualenv/virtualenv-%s.tar.gz"
                                 % (PYPI_URL, VENV_VERSION))

    log.info("Extracting virtualenv tarball.")
    unpack(venv_tarball_path)

    log.info("Creating virtualenv.")
    shellcmd("%s virtualenv-%s/virtualenv.py %s" % (sys.executable,
                                                    VENV_VERSION, venv))

    log.info("Installing virtualenv in virtualenv :) .")
    shellcmd("%s/bin/pip install virtualenv-%s/" % (venv, VENV_VERSION))


def bootstrap_ansible(venv='./venv'):
    """Install ansible inside virtualenv with no system-wide requirements"""

    if not os.path.isdir(venv):
        if os.path.exists(venv):
            log.error("Path '%s' exists and is not a directory, "
                      "it will be deleted.", venv)
            os.unlink(venv)
        bootstrap_venv(venv)

    log.info("Fetching ansible tarball.")
    ansible_tarball_path = download("%s/a/ansible/ansible-%s.tar.gz"
                                    % (PYPI_URL, ANSIBLE_VERSION))

    log.info("Extracting ansible tarball.")
    unpack(ansible_tarball_path)

    log.info("Removing pycrypto from ansible requirements.")
    shellcmd("sed -i \"s/, 'pycrypto[^']*'//\" ansible-%s/setup.py"
             % ANSIBLE_VERSION)

    log.info("Removing paramiko from ansible requirements.")
    shellcmd("sed -i \"s/'paramiko[^']*', //\" ansible-%s/setup.py"
             % ANSIBLE_VERSION)

    log.info("Installing ansible in virtualenv.")
    shellcmd("%s/bin/pip install ansible-%s/" % (venv, ANSIBLE_VERSION))

    log.info("Generate ansible inventory file for localhost.")
    with open("inventory", "w") as fobj:
        fobj.write("localhost ansible_connection=local "
                   "ansible_python_interpreter=%s\n" % sys.executable)

    log.info("Generate ansible.cfg.")
    with open("ansible.cfg", "w") as fobj:
        fobj.write("[defaults]\n"
                   "hostfile = inventory\n"
                   "nocows = 1\n")


def run_ansible_playbook(path, params=''):
    """Execute an ansible playbook inside a temporary python virtualenv"""
    player = "venv/bin/ansible-playbook"
    if not os.path.isfile(player):
        bootstrap_ansible()
    cmd = "%s %s" % (player, path)
    if params:
        cmd += ' -e "%s"' % params.replace('"', r'\"')
    return shellcmd(cmd, break_on_error=False)


def run_executable_file(path, params=''):
    """Run a script"""
    os.chmod(path, 0700)
    cmd = path
    if "--mist-export-params" in params:
        paramsarray = params.split()
        export = False
        exportcmd = ""
        paramsarrayremove = []
        for p in paramsarray:
            print(p)
            if p == "--mist-export-params" or export:
                if export:
                    if p.startswith("-") or p.startswith("--"):
                        export = False
                        break
                    elif p.find("=") != -1:
                        print(exportcmd)
                        exportcmd += "export {0};".format(p)
                        paramsarrayremove.append(p)
                else:
                    paramsarrayremove.append(p)
                    export = True
        if exportcmd:
            cmd = exportcmd + cmd
        for p in paramsarrayremove:
            paramsarray.remove(p)
            params = " ".join(paramsarray)
    if params:
        cmd += " %s" % params
    return shellcmd(cmd, break_on_error=False)


def bootstrap_template(blueprint, inputs):

    path = find_folder('scripts')
    os.chdir(path)
    f = open("inputs.yaml", "wb")
    f.write(inputs)
    f.close()

    shellcmd("virtualenv env", break_on_error=False)
    shellcmd("env/bin/pip install cloudify", break_on_error=False)
    shellcmd("env/bin/pip install -r dev-requirements.txt")
    cmd = 'env/bin/cfy local init -p {0} -i inputs.yaml'.format(blueprint)
    return shellcmd(cmd, break_on_error=False)


def run_template(workflow):
    cmd = "env/bin/cfy local execute -w {0}".format(workflow)
    return shellcmd(cmd, break_on_error=False)


def parse_args():
    """Parse command line arguments"""
    try:
        import argparse
        parser = argparse.ArgumentParser(
            description="Fetch and run executable script or ansible playbook.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument('script',
                            help="Url or path of script location.")
        parser.add_argument(
            '-f', '--file', type=str,
            help="If script is a tar or zip archive, optionally specify "
                 "relative path of script file inside archive.")
        parser.add_argument('-p', '--params', type=str,
                            help="String of params to pass to script.")
        parser.add_argument('-a', '--ansible', action='store_true',
                            help="Treat script as an ansible playbook.")
        parser.add_argument('-t', '--template', action='store_true',
                            help="Treat script as an orchestation template.")
        parser.add_argument('-w', '--workflow', type=str, default='install',
                            help="Run workflow on orchestration template.")
        parser.add_argument('-v', '--verbose', action='store_true',
                            help="Show debug logs.")
        args = parser.parse_args()
    except ImportError:
        # Python 2.6 does not have argparse
        import optparse
        parser = optparse.OptionParser("usage: %prog [options] script")
        parser.add_option(
            '-f', '--file', type=str,
            help="If script is a tar or zip archive, optionally specify "
                 "relative path of script file inside archive.")
        parser.add_option('-p', '--params', type=str,
                          help="String of params to pass to script.")
        parser.add_option('-a', '--ansible', action='store_true',
                          help="Treat script as an ansible playbook.")
        parser.add_option('-t', '--template', action='store_true',
                          help="Treat script as an orchestation template.")
        parser.add_option('-w', '--workflow', type=str,
                          help="Run workflow on orchestration template.")
        parser.add_option('-v', '--verbose', action='store_true',
                          help="Show debug logs.")
        args, list_args = parser.parse_args()
        args.script = list_args[0]
    return args


def main():
    """Fetch and run executable script or ansible playbook"""

    args = parse_args()

    loglvl = logging.DEBUG if args.verbose else logging.INFO
    logfmt = "[%(asctime)-15s][%(levelname)s] - %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(logfmt))
    handler.setLevel(loglvl)  # Overridden by configuration
    log.addHandler(handler)
    log.setLevel(loglvl)

    randid = '%x' % random.randrange(2 ** 128)
    mksep = lambda part: '-----part-%s-%s-----' % (part, randid)
    print mksep('bootstrap')

    try:
        if os.path.isfile(args.script):
            # resolve possibly relative script path before changing working dir
            args.script = os.path.abspath(args.script)

        tmpdir = tempfile.mkdtemp()
        log.info("Will work in temporary directory '%s'.", tmpdir)
        os.chdir(tmpdir)

        if os.path.isfile(args.script):
            path = args.script
        else:
            path = download(args.script)
        try:
            unpack(path, 'scripts/')
        except:
            pass
        else:
            path = find_path('scripts', args.file)
        if args.ansible:
            bootstrap_ansible()
            run = run_ansible_playbook
        elif args.template:
            inputs = ""
            if args.params:
                inputs = args.params
            bootstrap_template(path, inputs)
            run = run_template
        else:
            run = run_executable_file
        print mksep('end')
        print mksep('script')
        if args.template:
            exit_code = run(args.workflow)
            os.chdir(tmpdir)
        else:
            exit_code = run(path, args.params)
        out_paths = ('output', os.path.join(os.path.dirname(path), 'output'))
        for out_path in out_paths:
            if os.path.isfile(out_path):
                print mksep('end')
                print mksep('outfile')
                try:
                    with open(out_path) as fobj:
                        print fobj.read()
                except Exception as exc:
                    log.error("Error reading '%s' file: %r", out_path, exc)
                break
        print mksep('end')
        print mksep('summary')
        log.info("Wrapper script execution completed successfully. "
                 "User script exited with rc %s." % exit_code)
        print mksep('end')
        return exit_code
    except Exception as exc:
        print mksep('end')
        print mksep('summary')
        log.critical(exc)
        print mksep('end')
        return -1


if __name__ == "__main__":
    sys.exit(main())
