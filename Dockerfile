# Set Python version.
FROM python:3.10

# Create working directory.
WORKDIR /bot/
COPY ./ /bot/

# Install dependencies.
RUN apt-get update
RUN apt-get install -y ffmpeg
RUN pip install -r ./requirements.txt

# Run bot.
CMD python3 ./src/main.py
