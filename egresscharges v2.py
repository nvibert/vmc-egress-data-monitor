#!/usr/bin/env python3

"""

Welcome to the VMC Egress Charges Calculator ! 

You can install python 3.8 from https://www.python.org/downloads/windows/ (Windows) or https://www.python.org/downloads/mac-osx/ (MacOs).

You can install the dependent python packages locally (handy for Lambda) with:
pip3 install requests or pip3 install requests -t . --upgrade
pip3 install configparser or pip3 install configparser -t . --upgrade
"""

import requests                         # need this for Get/Post/Delete
import configparser                     # parsing config file
import time
from time import gmtime, strftime
from datetime import datetime
import sys
from prettytable import PrettyTable
from wavefront_sdk import WavefrontProxyClient


config = configparser.ConfigParser()
config.read("./config.ini")
strProdURL      = config.get("vmcConfig", "strProdURL")
strCSPProdURL   = config.get("vmcConfig", "strCSPProdURL")
Refresh_Token   = config.get("vmcConfig", "refresh_Token")
ORG_ID          = config.get("vmcConfig", "org_id")
SDDC_ID         = config.get("vmcConfig", "sddc_id")




class data():
    sddc_name       = ""
    sddc_status     = ""
    sddc_region     = ""
    sddc_cluster    = ""
    sddc_hosts      = 0
    sddc_type       = ""

def getAccessToken(myKey):
    """ Gets the Access Token using the Refresh Token """
    params = {'refresh_token': myKey}
    headers = {'Content-Type': 'application/json'}
    response = requests.post('https://console.cloud.vmware.com/csp/gateway/am/api/auth/api-tokens/authorize', params=params, headers=headers)
    jsonResponse = response.json()
    access_token = jsonResponse['access_token']
    return access_token

def getNSXTproxy(org_id, sddc_id, sessiontoken):
    """ Gets the Reverse Proxy URL """
    myHeader = {'csp-auth-token': sessiontoken}
    myURL = "{}/vmc/api/orgs/{}/sddcs/{}".format(strProdURL, org_id, sddc_id)
    response = requests.get(myURL, headers=myHeader)
    json_response = response.json()
    proxy_url = json_response['resource_config']['nsx_api_public_endpoint_url']
    return proxy_url

def getSDDCEdgeCluster(proxy_url, sessiontoken):
    """ Gets the Edge Cluster ID """
    myHeader = {'csp-auth-token': sessiontoken}
    proxy_url_short = proxy_url.rstrip("/sks-nsxt-manager")
    myURL = (proxy_url_short + "/policy/api/v1/infra/sites/default/enforcement-points/vmc-enforcementpoint/edge-clusters")
    response = requests.get(myURL, headers=myHeader)
    json_response = response.json()
    edge_cluster_id = json_response['results'][0]['id']
    return edge_cluster_id

def getSDDCEdgeNodes(proxy_url, sessiontoken, edge_cluster_id,edge_id):
    """ Gets the Edge Nodes Path """
    myHeader = {'csp-auth-token': sessiontoken}
    proxy_url_short = proxy_url.rstrip("/sks-nsxt-manager")
    myURL = proxy_url_short + "/policy/api/v1/infra/sites/default/enforcement-points/vmc-enforcementpoint/edge-clusters/" + edge_cluster_id + "/edge-nodes"
    response = requests.get(myURL, headers=myHeader)
    json_response = response.json()
    json_response_status_code = response.status_code
    if json_response_status_code == 200:
        edge_path = json_response['results'][edge_id]['path']
        return edge_path
    else:
        print("fail")
    
def getSDDCInternetStats(proxy_url, sessiontoken, edge_path):
    ### Displays counters for egress interface ###
    myHeader = {'csp-auth-token': sessiontoken}
    proxy_url_short = proxy_url.rstrip("/sks-nsxt-manager")
    myURL = (proxy_url_short + "/policy/api/v1/infra/tier-0s/vmc/locale-services/default/interfaces/public-0/statistics?edge_path=" + edge_path + "&enforcement_point_path=/infra/sites/default/enforcement-points/vmc-enforcementpoint")
    response = requests.get(myURL, headers=myHeader)
    json_response = response.json()
    json_response_status_code = response.status_code
    if json_response_status_code == 200:
        total_bytes = json_response['per_node_statistics'][0]['tx']['total_bytes']
        return total_bytes      
    else:
        print("fail")

wavefront_sender = WavefrontProxyClient(
   host="ec2-A-B-C-D.eu-west-2.compute.amazonaws.com",
   metrics_port=2878,
   distribution_port=2878,
   tracing_port=30000,
)
# --------------------------------------------
# ---------------- Main ----------------------
# --------------------------------------------

session_token = getAccessToken(Refresh_Token)
proxy = getNSXTproxy(ORG_ID, SDDC_ID, session_token)
edge_cluster_id = getSDDCEdgeCluster(proxy, session_token)
edge_path_0 = getSDDCEdgeNodes(proxy, session_token, edge_cluster_id, 0)
edge_path_1 = getSDDCEdgeNodes(proxy, session_token, edge_cluster_id, 1)

while True:
     session_token = getAccessToken(Refresh_Token)
     proxy = getNSXTproxy(ORG_ID, SDDC_ID, session_token)
     now = datetime.now()
     timestamp = datetime.timestamp(now)
     stat_0 = getSDDCInternetStats(proxy,session_token, edge_path_0)
     stat_1 = getSDDCInternetStats(proxy,session_token, edge_path_1)
     total_stat = stat_0 + stat_1
     print("Current Total Bytes count on Internet interface is " + str(total_stat) + " Bytes.")
     wavefront_sender.send_metric(name="sddc_egress_data", value=total_stat, tags={"sddc":"vmc-early-access"}, timestamp=timestamp,source="nvibert_sddc_early_access")
     print(strftime("%Y-%m-%d %H:%M:%S", gmtime()))
     time.sleep(30)
