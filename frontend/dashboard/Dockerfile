# Simple HTTP server for static dashboard
FROM nginx:alpine

# Copy dashboard files
COPY . /usr/share/nginx/html

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
