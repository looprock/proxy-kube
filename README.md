# proxy-kube
a local kube-proxy emulator which uses pykube and haproxy to create localhost addresses and /etc/hosts entries for pods in a kubernetes cluster.

IMPORTANT: you must be able to route to the pods for this to be useful!

# Caveats
proxy-kube currently only supports a single namespace per context. Since it's only set up to serve short name (vs FQDN)
names in /etc/hosts the dependency chain would be too difficult to manage

# Usage

You can get help with the -h flag:

```$ ./proxy-kube.py -h
usage: proxy-kube.py [-h] [-c CONTEXT] [-e EXCLUDE] [-n NAMESPACE]

optional arguments:
  -h, --help            show this help message and exit
  -c CONTEXT, --context CONTEXT
                        specify context
  -e EXCLUDE, --exclude EXCLUDE
                        specify exclude
  -n NAMESPACE, --namespace NAMESPACE
                        specify namespace```

For the simplest case you only need to provide a context via command-line

```$ ./proxy-kube.py -c minikube
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
