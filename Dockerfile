# Made updates based on recommendations from: https://pythonspeed.com/articles/root-capabilities-docker-security/

FROM python:3.10-slim-buster

# create a new user to run the bot
RUN groupadd -r botuser \
    && useradd --no-log-init -r --create-home -g botuser botuser 

# Update linux packages
RUN apt-get update && \
    apt-get upgrade -y 

WORKDIR /home/botuser

# copy project files
COPY advent_bot.py /home/botuser
COPY requirements.txt /tmp

# install requirements
RUN pip3 install -r /tmp/requirements.txt

# create volume for persistent storage
# RUN mkdir -p -m 777 /shared \
#     && chown botuser:botuser /shared

# run as botuser instead of root
USER botuser

CMD ["python3", "advent_bot.py"]
