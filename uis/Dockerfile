FROM node:22-alpine

WORKDIR /uis

COPY website/package.json website/package-lock.json ./website/
COPY backoffice/package.json backoffice/package-lock.json ./backoffice/
RUN cd website && npm ci && npm cache clean --force && cd ../backoffice && npm ci && npm cache clean --force

COPY website ./website
COPY backoffice ./backoffice
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

EXPOSE 3000 3001
CMD ["sh", "./start.sh"]