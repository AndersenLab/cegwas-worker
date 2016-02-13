FROM rocker/hadleyverse

# Homebrew
RUN apt-get update
RUN apt-get install -y curl g++ gawk m4 make patch ruby tcl wget build-essential curl\
	default-jdk gawk gfortran git m4 ruby texinfo unzip \
	libbz2-dev libcurl4-openssl-dev libexpat-dev libncurses-dev zlib1g-dev \
	python-setuptools python-dev python-pip libpng-dev libjpeg-dev libssl-dev

RUN pip install httplib2 oauth2client google-api-python-client
RUN curl https://dl.google.com/dl/cloudsdk/release/install_google_cloud_sdk.bash | bash
RUN exec $SHELL
RUN useradd -m -s /bin/bash linuxbrew
RUN echo 'linuxbrew ALL=(ALL) NOPASSWD:ALL' >>/etc/sudoers
USER linuxbrew
WORKDIR /home/linuxbrew
ENV PATH /home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:$PATH
ENV SHELL /bin/bash
RUN yes |ruby -e "$(curl -fsSL https://raw.github.com/Homebrew/linuxbrew/go/install)"
RUN brew doctor || true
RUN brew tap homebrew/science
RUN brew install htslib
RUN brew install samtools
RUN wget https://github.com/samtools/bcftools/releases/download/1.3/bcftools-1.3.tar.bz2
RUN tar xvjf bcftools-1.3.tar.bz2
RUN cd bcftools-1.3 && make && mv ./bcftools /home/linuxbrew/.linuxbrew/bin/bcftools

# Install Cegwas
USER root
RUN R --vanilla -e "devtools::install_github('rstudio/DT')"
RUN R --vanilla -e "devtools::install_github('Andersenlab/cegwas')"
MAINTAINER Daniel Cook <danielecook@gmail.com>
