# cegwas-web-worker

### Setup

rm worker.zip
zip -r worker.zip *
iron worker upload --zip worker.zip --name map danielecook/cegwas-worker bash run.sh
iron worker queue map

# Testing
docker run -e PAYLOAD_FILE="test_payload.json" -ti --rm -v "$(pwd)":/home/docker -w /home/docker danielecook/cegwas-worker bash run.sh


# Installing packages

Rscript -e "devtools::with_libpaths(new = './Rpackages', devtools::install_github('Andersenlab/cegwas'))"
Rscript -e "install.packages('dplyr', lib = './Rpackages')"



iron/r-base