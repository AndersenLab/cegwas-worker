import httplib2
import base64
import json
from apiclient import discovery
from oauth2client import client as oauth2client
from subprocess import check_output
from iron_mq import *
from models import *


# Get instance information
#import requests
#metadata_server = "http://metadata/computeMetadata/v1/instance/"
#metadata_flavor = {'Metadata-Flavor' : 'Google'}
#gce_id = requests.get(metadata_server + 'id', headers = metadata_flavor).text
#gce_name = requests.get(metadata_server + 'hostname', headers = metadata_flavor).text
#
#worker_status.get_or_create(machine_id = gce_id, machine_name = gce_name)

queue = IronMQ().queue("cegwas-map")

while True:

    resp = queue.reserve(timeout=3600)["messages"]

    if len(resp) > 0:
        message = resp[0]

        # Acknowledge reciept of message
        args = message["body"]
        data = json.loads(args)
        report_slug = data["report_slug"]
        trait_slug = data["trait_slug"]
        report_id = report.get(report_slug = report_slug).id
        # Run workflow
        comm = """Rscript -e "rmarkdown::render('report.Rmd')" '{args}'""".format(args = args)
        try:
            print comm
            check_output(comm, shell = True)

            # Upload results
            upload1 = """gsutil cp report.html gs://cendr/{report_slug}/{trait_slug}/report.html""".format(**locals())
            check_output(upload1, shell = True)
            upload2 = """gsutil cp -r figures gs://cendr/{report_slug}/{trait_slug}/""".format(**locals())
            check_output(upload2, shell = True)

            # Update status of report submission
            trait.update(submission_complete=datetime.datetime.now(), status="complete").where(trait.report == report_id, trait.trait_slug == trait_slug).execute()
        except:
            trait.update(submission_complete=datetime.datetime.now(), status="error").where(trait.report == report_id, trait.trait_slug == trait_slug).execute()
        queue.delete(message["id"], message["reservation_id"])

        


