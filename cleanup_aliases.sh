#!/bin/sh
# this should match localif_prefix in proxy-kube.py
localipr="10.214.0"
for i in `ifconfig lo0 |grep ${localipr} |awk {'print $2'}`
do 
	sudo ifconfig lo0 -alias $i
done
