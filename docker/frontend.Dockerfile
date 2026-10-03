#dev: vite dev server with hot reload (the source folder is bind mounted by compose)
FROM node:22-alpine AS dev
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

#build + prod: static files served by nginx, used for deployment later
FROM dev AS build
ARG VITE_API_URL=http://localhost:8001
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
