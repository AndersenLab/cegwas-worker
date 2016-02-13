#/bin/bash
Rscript -e "rmarkdown::render('report.Rmd')"
/root/google-cloud-sdk/bin/gcloud auth activate-service-account --key-file service-account.json

/root/google-cloud-sdk/bin/gcloud config set project andersen-lab

trait_name=`cat ${PAYLOAD_FILE} | python -c 'import json,sys;obj=json.load(sys.stdin);print obj["trait_name"]'`
report_slug=`cat ${PAYLOAD_FILE} | python -c 'import json,sys;obj=json.load(sys.stdin);print obj["report_info"]["report_slug"]'`

/root/google-cloud-sdk/bin/gsutil cp report.html gs://cendr/${report_slug}/${trait_name}/report.html
/root/google-cloud-sdk/bin/gsutil cp -r figures gs://cendr/${report_slug}/${trait_name}/
