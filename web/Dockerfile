# Build stage
FROM node:20-alpine AS build
WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci

# Copy source code and build
COPY . .
# Cấu hình production (mặc định của angular.json): fileReplacements đổi sang
# environment.prod.ts nên bundle browser gọi API qua `/api` cùng origin, do
# proxy trong server.ts chuyển tiếp. Không nhúng cứng `http://localhost:8000`
# vào bundle — địa chỉ đó là máy của người dùng cuối, không phải server.
RUN npm run build

# Run stage
FROM node:20-alpine
WORKDIR /app

# Copy the built artifacts from the build stage
COPY --from=build /app/dist /app/dist
COPY package.json ./

EXPOSE 4000
CMD ["npm", "run", "serve:ssr:web"]
