#!/usr/bin/env python
import pykube
import operator
from os.path import expanduser, exists
import json
import sh
import re
import sys
import os
import getpass
import configparser



domain = "default.svc.beta.local"

home = expanduser("~")
kubeconfig = "%s/.kube/config" % home
proxydir = "%s/.proxy-kube" % home

if not os.path.exists(proxydir):
    os.mkdir(proxydir)

proxyconfig = "%s/config" % proxydir
haproxy_config = "%s/haproxy.conf" % proxydir

local_services = []

if os.path.exists(proxyconfig):
    config = configparser.ConfigParser()
    config.read(proxyconfig)
    if 'default' in config:
        if 'local' in config['default']:
            for i in config.get('default', 'local').split(','):
                local_services.append(i.strip())
        print("Excluding mappings for local services:")
        for i in local_services:
            print(i)
        print("")


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
# print(chkcom("bar"))



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


# exclude list should live in proxyconfig:
# do NOT proxy things living in local part of proxy config

# exclude services via flag

# https://github.com/kelproject/pykube
# set up watches to notice changes

# sudo ifconfig lo0 alias 127.0.0.2
# create haproxy entry for each service mapped to localhost IP and backend port
# use ghost to manage /etc/hosts:
# https://superuser.com/questions/381138/mac-os-x-hosts-file-can-i-include-other-files-with-it

# need both start and stop commands:
# start: create config, add hosts w/ ghost, start haproxy
# stop: stop haproxy, remove ghost entries

# don't forget:
# object.__dict

api = pykube.HTTPClient(pykube.KubeConfig.from_file(kubeconfig))

def config():
    print("(Re)configuring haproxy configuration and host entries..")
    # services = pykube.Service.objects(api).filter(field_selector={"metadata.name":"homefit"})
    services = pykube.Service.objects(api)
    service_list = {}
    for service in services:
        port_list = []
        # print(service)
        sobj = service.obj
        spec = sobj['spec']
        # print(spec)
        if 'selector' in spec.keys():
            tmpdict = {}
            # print(spec['selector'])
            # print(spec['ports'])
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

    # print(json.dumps(service_list, indent=4))

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
    curip = 1
    for service in service_list.keys():
        if service not in local_services:
            localif = "127.15.0.%s" % (str(curip))
            if findif(localif):
                print(findif(localif))
            # print("### creating mapping for service: %s" % service)
            # print(service_list[service]['ports'].keys())
            for pname in service_list[service]['ports'].keys():
                if service_list[service]['ports'][pname]:
                    # 10.1.5.16	elasticsearch-0.es-cluster.default.svc.cluster.local	elasticsearch-0
                    output = sh.sudo("ghost", "add", service, localif)
                    # if output.exit_code
                    # print("Service: %s" % service)
                    # print("pname: %s" % pname)
                    # print("curip: %s" % str(curip))
                    # print("port: %s" % service_list[service]['ports'][pname]['port'])
                    config += """
    frontend %s-%s
        bind %s:%s
        mode tcp
        default_backend %s-%s

    backend %s-%s
        mode tcp
        balance roundrobin\n""" % (service, pname, localif, str(service_list[service]['ports'][pname]['port']), service, pname, service, pname)
            # print(service)
                pods = pykube.Pod.objects(api).filter(selector=service_list[service]['selectors'])
                for i in pods:
                    # print(service_list[service]['ports'][pname])
                    pod = i.obj
                    config += "        server %s %s:%s\n" % (str(pod['status']['podIP']), str(pod['status']['podIP']), str(service_list[service]['ports'][pname]['targetPort']))
                #     # print(pod['spec']['ports'])
                #     for port in service_list[service]['ports']:
                #         print("     %s:%s" % (pod['status']['podIP'], port))
                config += "\n"
                curip = curip + 1

    target = open(haproxy_config, 'w')
    target.write(config)
    target.close()

def up():
    config()
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
        watch = pykube.Pod.objects(api).watch()
        for watch_event in watch:
            if not re.search(re.escape("wolfnet-importer"), str(watch_event[1])):
                if str(watch_event[1]) not in seen:
                    if str(watch_event[0]) != 'ADDED': # 'ADDED', 'DELETED', 'MODIFIED'
                        # print(watch_event)
                        print("Event triggered from: %s" % (str(watch_event[1])))
                        config()
                        kill()
                        launch()
                        seen.append(str(watch_event[1]))

    except KeyboardInterrupt:
        down()
        sys.exit()
