#!/usr/bin/env python3
import pykube
import operator
from os.path import expanduser, exists
import json
import sh
import re
import sys
import os
import yaml
import argparse
import shutil

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--context", help="specify context")
parser.add_argument("-e", "--exclude", help="specify exclude")
parser.add_argument("-n", "--namespace", help="specify namespace")
args = parser.parse_args()
pconfig = {}
if args.context:
    pconfig[args.context] = {}
    if args.exclude:
        pconfig[args.context]['exclude'] = args.exclude.split(",")
    if args.namespace:
        pconfig[args.context]['namespace'] = 'default'

    print("Using CLI overrides, trying to build out config...")
    print("context: %s" % args.context)

# https://github.com/kelproject/pykube
# set up watches to notice changes

# use ghost to manage /etc/hosts:
# https://superuser.com/questions/381138/mac-os-x-hosts-file-can-i-include-other-files-with-it

# support multiple namespaces
# create kube External service definitions
# remove localif interface aliases in cleanup

# domain = "default.svc.beta.local"
localif_prefix = "10.214.0"

home = expanduser("~")
kubeconfig = "%s/.kube/config" % home
proxydir = "%s/.proxy-kube" % home
svctmp = "%s/svc" % proxydir
if not os.path.exists(proxydir):
    os.mkdir(proxydir)
if not os.path.exists(svctmp):
    os.mkdir(svctmp)

proxyconfig = "%s/config.yaml" % proxydir
haproxy_config = "%s/haproxy.conf" % proxydir

if not pconfig:
    if os.path.exists(proxyconfig):
        with open(proxyconfig, 'r') as stream:
            try:
                pconfig=yaml.load(stream)
            except yaml.YAMLError as exc:
                print(exc)

if not pconfig:
    print("ERROR: you must provide a context, either in %s or via command line!" % proxyconfig)
    sys.exit(1)

# print(pconfig)

# normalize config data
for kube_context in pconfig.keys():
    # print(list(pconfig[kube_context].keys()))
    if 'namespace' not in list(pconfig[kube_context].keys()):
        print("Setting namespace to default...")
        pconfig[kube_context]['namespace'] = 'default'
    if 'exclude' not in list(pconfig[kube_context].keys()):
        pconfig[kube_context]['exclude'] = []

# print(json.dumps(pconfig,indent=4))

def chkcom(command):
    if command == "haproxy":
        if not sh.brew("list", command):
            if sh.which('brew'):
                output = sh.brew("install", command)
                return(output.exit_code)
            else:
                return("# ERROR: cannot find command %s and brew isn't installed, aborting")
    elif command == "ghost":
        if not sh.which('ghost'):
            output = sh.sudo("gem", "install", command)
            return(output.exit_code)

if chkcom("haproxy"):
    print(chkcom("haproxy"))

if chkcom("ghost"):
    print(chkcom("ghost"))

ifaces = sh.ifconfig("lo0")

def findif(iface):
    if not re.search(re.escape(iface), str(ifaces), re.IGNORECASE):
        try:
            output = sh.sudo("ifconfig", "lo0", "alias", iface)
            return(output.exit_code)
        except:
            return("# ERROR: Failed to add lo0 alias!")

def launch():
    print("Launching haproxy")
    sh.sudo("haproxy", "-f", haproxy_config, _fg=True)

def build_config(start=False):
    config = """global
   log 127.0.0.1 local2
   daemon
   maxconn 256

defaults
   log global
   timeout connect  5000
   timeout client  10000
   timeout server  10000

listen stats
   bind :1936
   mode http
   stats enable
   stats hide-version
   stats realm Haproxy\ Statistics
   stats uri /
   stats auth admin:admin
\n
"""
    print("(Re)configuring haproxy configuration and host entries..")
    all_services = []
    curip = 2
    for kube_context in pconfig.keys():
        print("Configuring context: %s" % (kube_context))
        pykube_config = pykube.KubeConfig.from_file(kubeconfig)
        pykube_config.set_current_context(kube_context)
        api = pykube.HTTPClient(pykube_config)
        services = pykube.Service.objects(api).filter(namespace=pconfig[kube_context]['namespace'])
        service_list = {}
        for service in services:
            # print(pconfig[kube_context]['exclude'])
            if str(service) not in pconfig[kube_context]['exclude']:
                if str(service) in all_services:
                    print("ERROR: found service %s in multiple contexts! Please use excludes to isolate all but one!" % service)
                    sys.exit(1)
                port_list = []
                sobj = service.obj
                spec = sobj['spec']
                if 'selector' in spec.keys():
                    tmpdict = {}
                    for port in spec['ports']:
                        # {'name': 'http', 'protocol': 'TCP', 'port': 80, 'targetPort': 80}
                        # {'protocol': 'TCP', 'port': 5432, 'targetPort': 5432}
                        if str(port['targetPort']).isdigit():
                            if 'name' in port:
                                name = port['name']
                            else:
                                name = 'default'
                            tmpdict[name] = {}
                            if str(kube_context) == "minikube":
                                tmpdict[name]['nodePort'] = port['nodePort']
                            tmpdict[name]['protocol'] = port['protocol']
                            tmpdict[name]['port'] = port['port']
                            tmpdict[name]['targetPort'] = port['targetPort']
                    if tmpdict:
                        service_list[str(service)] = {}
                        service_list[str(service)]['ports'] = tmpdict
                        service_list[str(service)]['selectors'] = spec['selector']

        for service in service_list.keys():
            if str(service) not in pconfig[kube_context]['exclude']:
                all_services.append(str(service))
                localif = "%s.%s" % (localif_prefix, str(curip))
                if findif(localif):
                    print(findif(localif))
                svctmpl = """apiVersion: v1
kind: Service
metadata:
  creationTimestamp: null
  name: %s
  namespace: %s
spec:
  externalName: %s
  sessionAffinity: None
  type: ExternalName
  ports:\n""" % (service, pconfig[kube_context]['namespace'], localif)
                for pname in service_list[service]['ports'].keys():
                    if start:
                        print("### creating mapping for service: %s:%s" % (service, str(service_list[service]['ports'][pname]['port'])))
                    if service_list[service]['ports'][pname]:
                        svctmpl += """  - name: %s
    port: %s
    protocol: TCP
    targetPort: %s\n""" % (pname, str(service_list[service]['ports'][pname]['port']), str(service_list[service]['ports'][pname]['targetPort']))

                        # 10.1.5.16	elasticsearch-0.es-cluster.default.svc.cluster.local	elasticsearch-0
                        output = sh.sudo("ghost", "add", service, localif)
                        config += """
frontend %s-%s
    bind %s:%s
    mode tcp
    default_backend %s-%s

backend %s-%s
    mode tcp
    balance roundrobin\n""" % (service, pname, localif, str(service_list[service]['ports'][pname]['port']), service, pname, service, pname)
                    pods = pykube.Pod.objects(api).filter(namespace=pconfig[kube_context]['namespace'], selector=service_list[service]['selectors'])
                    for i in pods:
                        pod = i.obj
                        if kube_context == 'minikube':
                            targetIP = str(pod['status']['hostIP'])
                            targetPort = str(service_list[service]['ports'][pname]['nodePort'])
                        else:
                            targetIP = str(pod['status']['podIP'])
                            targetPort = str(service_list[service]['ports'][pname]['targetPort'])
                        config += "    server %s %s:%s\n" % (targetIP, targetIP, targetPort)
                    config += "\n"
                    curip = curip + 1
                if kube_context != "minikube":
                    svcout = "%s/%s.yaml" % (svctmp, service)
                    target = open(svcout, 'w')
                    target.write(svctmpl)
                    target.close()
        target = open(haproxy_config, 'w')
        target.write(config)
        target.close()
        manage_minikube_svc('apply')

def up():
    build_config(start=True)
    manage_minikube_svc('apply')
    launch()

def kill():
    print("Attempting to kill haproxy..")
    try:
        sh.sudo("killall", "haproxy")
    except:
        pass

def rmaliases():
    print("Removing interface aliases..")
    x = sh.ifconfig("lo0")
    for i in x.split("\n"):
        print(i)
        matchobj = re.match( r'^\W+inet\W+(' + re.escape(localif_prefix) + '\.\d+)\W+.*$', i)
        if matchobj:
            ip = matchobj.group(1)
            print("Removing %s" % str(ip))
            try:
                output = sh.sudo("ifconfig", "lo0", "-alias", str(ip))
                return(output.exit_code)
            except:
                return("# ERROR: Failed to remove lo0 alias %s!" % (str(ip)))

def manage_minikube_svc(action):
    if 'minikube' in list(pconfig.keys()):
        if 'loadsvc' in list(pconfig['minikube'].keys()):
            print("%s services in minikube..." % (action))
            try:
                output = sh.kubectl('config', 'use-context', 'minikube')
                # print(output)
                output = sh.minikube_services(action)
                print(output)
            except sh.ErrorReturnCode as e:
                print("ERROR: minikube-services unable to %s services" % (action))
                print(e.stderr)

def down():
    print("Cleaning up")
    sh.sudo("ghost", "empty")
    kill()
    sh.rm(haproxy_config)
    manage_minikube_svc('delete')
    shutil.rmtree(svctmp)
    # rmaliases()

if __name__ == '__main__':
    try:
        up()
        seen = []
        watch_context = None
        if len(pconfig.keys()) > 1:
            for test_context in pconfig.keys():
                if 'watch' in pconfig[test_context]:
                    if pconfig[test_context]['watch']:
                        watch_context = test_context
                        print("Found watch specified for context %s" % test_context)
            if not watch_context:
                print("Multiple contexts found in config, but watch not specified. Please specify 'watch: true' for one of them.")
                sys.exit(1)
        else:
            watch_context = list(pconfig.keys())[0]
        print("Context set to: %s" % (watch_context))
        watch_config = pykube.KubeConfig.from_file(kubeconfig)
        watch_config.set_current_context(watch_context)
        api = pykube.HTTPClient(watch_config)
        watch = pykube.Pod.objects(api).filter(namespace=pconfig[watch_context]['namespace']).watch()
        for watch_event in watch:
            if not re.search(re.escape("wolfnet-importer"), str(watch_event[1])):
                if str(watch_event[1]) not in seen:
                    if str(watch_event[0]) != 'ADDED': # 'ADDED', 'DELETED', 'MODIFIED'
                        print("Event triggered from: %s" % (str(watch_event[1])))
                        build_config()
                        kill()
                        launch()
                        seen.append(str(watch_event[1]))

    except KeyboardInterrupt:
        down()
        sys.exit()
