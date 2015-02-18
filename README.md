# Run script, run!

This script runs an executable script or ansible playbook on localhost.

Script can be given as a local path or remote url, in which case it is first
downloaded. It can optionally be contained inside a tarball or zip file,
in which case it is extracted on a temporary directory. If it is a simple
script, then it is made executable and run, if it's an ansible script, a python
virtualenv containing ansible is first created and used to run the playbook.
