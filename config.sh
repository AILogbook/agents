> sudo useradd -r -s /usr/sbin/nologin pdf-tools
> sudo chown -R pdf-tools:pdf-tools /root/agents/pdf_tools/uploads /root/agents/pdf_tools/outputs
> sudo systemctl daemon-reload && sudo systemctl restart pdf-tools
>