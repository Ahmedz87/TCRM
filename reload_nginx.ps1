# Post-renewal hook for win-acme: reload nginx so it picks up the new cert.
# nginx -s reload must be run from C:\nginx (prefix), per the project setup.
Set-Location C:\nginx
& .\nginx.exe -s reload -p C:\nginx
