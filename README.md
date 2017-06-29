# proxy-kube
a local kube-proxy emulator which uses pykube and haproxy to create localhost addresses and /etc/hosts entries for pods in a kubernetes cluster.

IMPORTANT: you must be able to route to the pods for this to be useful!

# Caveats
proxy-kube currently only supports a single namespace per context. Since it's only set up to serve short name (vs FQDN)
names in /etc/hosts the dependency chain would be too difficult to manage

# Requirements

## a working kubernetes install with a ~/.kube/config file.

## Set up sudo to support passwordless interaction

There are several ways to do this. The easiest is to execute 'sudo visudo' and add this line in /etc/sudoers:
```
%admin  ALL=(ALL) NOPASSWD: ALL
```


## Install dependencies
proxy-kube.py currently has dependencies on ghost, haproxy, and python3. This document assumes you'll install packages via brew.

### Packages
```
brew install python3 haproxy
sudo gem install ghost
pip3 install virtualenv
```

### Python modules and environment
virtualenv -p python3 ~/virtualenv/proxy-kube
source ~/virtualenv/proxy-kube/bin/activate
pip install -r requirements.txt


### Running proxy-kube.py
NOTE: you'll need to run:

```
source ~/virtualenv/proxy-kube/bin/activate
```

prior to executing this script from now on unless you do other things, like add that to your .bashrc or something..

Alternately You can use @tehviking suggestion and create a alias similar to:

```
alias proxy-kube='source ~/virtualenv/proxy-kube/bin/activate && /path/to/proxy-kube.py'
```

If you use minikube, you should also copy/link 'minikube_services' to somewhere like /usr/local/bin.

# Usage

You can get help with the -h flag:

```
$ ./proxy-kube.py -h
usage: proxy-kube.py [-h] [-c CONTEXT] [-e EXCLUDE] [-n NAMESPACE]

optional arguments:
  -h, --help            show this help message and exit
  -c CONTEXT, --context CONTEXT
                        specify context
  -e EXCLUDE, --exclude EXCLUDE
                        specify exclude
  -n NAMESPACE, --namespace NAMESPACE
                        specify namespace
```

For the simplest case you only need to provide a context via command-line

```
$ ./proxy-kube.py -c minikube
Using CLI overrides, trying to build out config...
context: minikube
Setting namespace to default...
(Re)configuring haproxy configuration and host entries..
Configuring context: minikube
### creating mapping for service: svc1:5000
### creating mapping for service: svc2:9000
### creating mapping for service: svc3:8080
Launching haproxy
Context set to: minikube
```

See config.yaml for more advanced configurations
