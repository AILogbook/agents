sudo useradd -r -s /usr/sbin/nologin pdf-tools
chown -R pdf-tools:pdf-tools /root/agents/pdf_tools/uploads /root/agents/pdf_tools/outputs
systemctl daemon-reload && sudo systemctl restart pdf-tools