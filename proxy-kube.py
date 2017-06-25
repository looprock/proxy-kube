#!/usr/bin/env python3
import pykube
import operator
from os.path import expanduser, exists
import json
import sh
import re
import sys
import os
import getpass
import yaml

# https://github.com/kelproject/pykube
# set up watches to notice changes

# use ghost to manage /etc/hosts:
# https://superuser.com/questions/381138/mac-os-x-hosts-file-can-i-include-other-files-with-it

# support multiple namespaces
# create kube External service definitions
# remove localif interface aliases in cleanup

domain = "default.svc.beta.local"
localif_prefix = "172.214.0"

home = expanduser("~")
kubeconfig = "%s/.kube/config" % home
proxydir = "%s/.proxy-kube" % home

if not os.path.exists(proxydir):
    os.mkdir(proxydir)

proxyconfig = "%s/config.yaml" % proxydir
haproxy_config = "%s/haproxy.conf" % proxydir

if os.path.exists(proxyconfig):
    with open(proxyconfig, 'r') as stream:
        try:
            pconfig=yaml.load(stream)
        except yaml.YAMLError as exc:
            print(exc)

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
    for kube_context in pconfig.keys():
        print("Context set to: %s" % (kube_context))
        pykube_config = pykube.KubeConfig.from_file(kubeconfig)
        pykube_config.set_current_context(kube_context)
        api = pykube.HTTPClient(pykube_config)
        services = pykube.Service.objects(api)
        service_list = {}
        for service in services:
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
                        tmpdict[name]['protocol'] = port['protocol']
                        tmpdict[name]['port'] = port['port']
                        tmpdict[name]['targetPort'] = port['targetPort']
                if tmpdict:
                    service_list[str(service)] = {}
                    service_list[str(service)]['ports'] = tmpdict
                    service_list[str(service)]['selectors'] = spec['selector']
        curip = 1
        for service in service_list.keys():
            if service not in pconfig[kube_context]['exclude']:
                all_services.append(str(service))
                localif = "%s.%s" % (localif_prefix, str(curip))
                if findif(localif):
                    print(findif(localif))
                if start:
                    print("### creating mapping for service: %s" % service)
                for pname in service_list[service]['ports'].keys():
                    if service_list[service]['ports'][pname]:
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
                    pods = pykube.Pod.objects(api).filter(selector=service_list[service]['selectors'])
                    for i in pods:
                        pod = i.obj
                        config += "    server %s %s:%s\n" % (str(pod['status']['podIP']), str(pod['status']['podIP']), str(service_list[service]['ports'][pname]['targetPort']))
                    config += "\n"
                    curip = curip + 1

        target = open(haproxy_config, 'w')
        target.write(config)
        target.close()

def up():
    build_config(start=True)
    launch()

def kill():
    print("Attempting to kill haproxy..")
    try:
        sh.sudo("killall", "haproxy")
    except:
        pass

def down():
    print("Cleaning up")
    sh.sudo("ghost", "empty")
    kill()
    sh.rm(haproxy_config)

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
        watch = pykube.Pod.objects(api).watch()
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
