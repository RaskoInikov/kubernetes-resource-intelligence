FROM python:3.12-alpine

WORKDIR /opt/kri
COPY __init__.py app.py load.py metrics.py /opt/kri/kri_workload/

USER 65532:65532
EXPOSE 8080
CMD ["python", "-m", "kri_workload.app"]
