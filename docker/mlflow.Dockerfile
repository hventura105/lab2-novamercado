FROM ghcr.io/mlflow/mlflow:v3.10.1
USER root
RUN mkdir -p /mlflow && chown -R 10001:0 /mlflow
USER 10001:0
ENV MLFLOW_TRACKING_URI=http://mlflow:5000 PYTHONUNBUFFERED=1
WORKDIR /mlflow
EXPOSE 5000
