#!/usr/bin/env bash
# Generates two nginx files from Cloudflare's published IP ranges. Run as root; re-run
# occasionally (e.g. a monthly cron job) because the ranges change.
#
#   /etc/nginx/snippets/cloudflare.conf   (include in a server block)
#       restores the real client IP from CF-Connecting-IP for requests via Cloudflare
#   /etc/nginx/conf.d/cloudflare-geo.conf (loaded at http level automatically)
#       sets $from_cloudflare to 1 when the connection itself comes from Cloudflare.
#       It reads $realip_remote_addr (the connecting address), not the restored client IP,
#       so a site can refuse direct connections that bypass Cloudflare with:
#           if ($from_cloudflare = 0) { return 403; }
set -euo pipefail
ranges=$(for v in 4 6; do curl -fsS "https://www.cloudflare.com/ips-v$v"; echo; done | grep -v '^$')
[ -n "$ranges" ] || { echo "no ranges downloaded" >&2; exit 1; }
stamp="# Generated $(date -u +%F) by update-cloudflare-ips.sh"

{
  echo "$stamp"
  while read -r cidr; do echo "set_real_ip_from $cidr;"; done <<< "$ranges"
  echo "real_ip_header CF-Connecting-IP;"
} > /etc/nginx/snippets/cloudflare.conf

{
  echo "$stamp"
  echo 'geo $realip_remote_addr $from_cloudflare {'
  echo '    default 0;'
  while read -r cidr; do echo "    $cidr 1;"; done <<< "$ranges"
  echo '}'
} > /etc/nginx/conf.d/cloudflare-geo.conf

nginx -t && systemctl reload nginx
echo "updated Cloudflare ranges"
