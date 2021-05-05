# Made updates based on recommendations from: https://pythonspeed.com/articles/root-capabilities-docker-security/

FROM python:3.8-slim-buster

# create a new user to run the bot
RUN useradd --create-home botuser 

# Update linux packages
RUN apt-get update && \
    apt-get upgrade -y 

# below for typ-ast error on alpine, see: https://github.com/PyCQA/pylint/issues/2291
#RUN apk add --no-cache --update python3-dev  gcc build-base

WORKDIR /home/botuser

# copy project files
COPY advent_bot.py /home/botuser
COPY requirements.txt /tmp

RUN pip3 install -r /tmp/requirements.txt

# run as botuser instead of root
USER botuser

CMD ["python3", "advent_bot.py"]
