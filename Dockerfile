FROM rocker/hadleyverse
FROM sjackman/linuxbrew
USER linuxbrew
RUN brew tap homebrew/science
RUN brew install samtools bcftools
MAINTAINER Daniel Cook <danielecook@gmail.com>