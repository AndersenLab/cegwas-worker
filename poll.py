import httplib2
import base64
import json
from apiclient import discovery
from oauth2client import client as oauth2client
from subprocess import check_output
from iron_mq import *

queue = IronMQ().queue("cegwas-map")

while True:

    resp = queue.get()["messages"]

    if len(resp) > 0:
        message = resp[0]
        print message["id"]

        # Acknowledge reciept of message
        args = message["body"]
        data = json.loads(args)
        report_slug = data["report_info"]["report_slug"]
        trait_name = data["trait_name"]
        # Run workflow
        comm = """Rscript -e "library(knitr); knit('report.Rmd')" '{args}'""".format(args = args)
        check_output(comm, shell = True)

        # Upload results
        upload1 = """gsutil cp report.html gs://cendr/{report_slug}/{trait_name}/report.html""".format(**locals())
        check_output(upload1, shell = True)
        upload2 = """gsutil cp -r figures gs://cendr/{report_slug}/{trait_name}/""".format(**locals())
        check_output(upload2, shell = True)
        #queue.delete(message["id"], message["reservation_id"])



