FROM python:3.12-alpine

WORKDIR /opt/kri
COPY app.py load.py /opt/kri/

USER 65532:65532
EXPOSE 8080
CMD ["python", "/opt/kri/app.py"]
