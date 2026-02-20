document.addEventListener("DOMContentLoaded", () => {

    // ===== Sidebar navigation =====
    document.querySelectorAll(".nav-item:not(.disabled)").forEach(item => {
        item.addEventListener("click", () => {
            document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
            item.classList.add("active");
            const panelId = item.dataset.panel;
            document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
            document.getElementById("panel-" + panelId).classList.add("active");
        });
    });

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
    }

    function renderResultFiles(container, files) {
        container.innerHTML = "";
        files.forEach(f => {
            const div = document.createElement("div");
            div.className = "result-file";
            div.innerHTML = `
                <div class="result-file-info">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <span>${f.name}</span>
                    <span class="page-count">(${f.page_count} 页)</span>
                </div>
                <a class="btn-download" href="${f.download_url}" download>
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    下载
                </a>`;
            container.appendChild(div);
        });
    }

    function setupToolPanel(cfg) {
        const uploadArea = document.getElementById(cfg.uploadAreaId);
        const fileInput = document.getElementById(cfg.fileInputId);
        const fileInfo = document.getElementById(cfg.fileInfoId);
        const fileNameEl = document.getElementById(cfg.fileNameId);
        const removeBtn = document.getElementById(cfg.removeBtnId);
        const processBtn = document.getElementById(cfg.processBtnId);
        const progressBar = document.getElementById(cfg.progressBarId);
        const resultCard = document.getElementById(cfg.resultCardId);
        const resultMeta = document.getElementById(cfg.resultMetaId);
        const resultFiles = document.getElementById(cfg.resultFilesId);
        const errorCard = document.getElementById(cfg.errorCardId);
        const errorText = document.getElementById(cfg.errorTextId);

        let selectedFile = null;

        function hideResults() {
            resultCard.style.display = "none";
            errorCard.style.display = "none";
            progressBar.style.display = "none";
        }

        function setFile(file) {
            selectedFile = file;
            fileNameEl.textContent = file.name + " (" + formatSize(file.size) + ")";
            uploadArea.style.display = "none";
            fileInfo.style.display = "block";
            processBtn.disabled = false;
            hideResults();
        }

        function clearFile() {
            selectedFile = null;
            fileInput.value = "";
            uploadArea.style.display = "";
            fileInfo.style.display = "none";
            processBtn.disabled = true;
            hideResults();
        }

        uploadArea.addEventListener("dragover", e => {
            e.preventDefault();
            uploadArea.classList.add("drag-over");
        });
        uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("drag-over"));
        uploadArea.addEventListener("drop", e => {
            e.preventDefault();
            uploadArea.classList.remove("drag-over");
            const files = e.dataTransfer.files;
            if (files.length > 0 && files[0].name.toLowerCase().endsWith(".pdf")) {
                setFile(files[0]);
            }
        });
        uploadArea.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", () => {
            if (fileInput.files.length > 0) setFile(fileInput.files[0]);
        });
        removeBtn.addEventListener("click", e => {
            e.stopPropagation();
            clearFile();
        });

        const progressFill = progressBar.querySelector(".progress-fill");
        const progressText = progressBar.querySelector(".progress-text");

        function showResult(data, status) {
            progressBar.style.display = "none";
            progressFill.classList.remove("indeterminate");
            if (status >= 400 || !data.success) {
                errorCard.style.display = "block";
                errorText.textContent = data.error || "处理失败，请重试";
            } else {
                resultMeta.innerHTML =
                    `文档总页数: <strong>${data.total_pages}</strong> 页 &nbsp;|&nbsp; 处理范围: 第 <strong>${data.range}</strong> 页`;
                renderResultFiles(resultFiles, data.files);
                resultCard.style.display = "block";
            }
            processBtn.disabled = false;
        }

        function showError(msg) {
            progressBar.style.display = "none";
            progressFill.classList.remove("indeterminate");
            errorCard.style.display = "block";
            errorText.textContent = msg;
            processBtn.disabled = false;
        }

        processBtn.addEventListener("click", () => {
            if (!selectedFile) return;
            hideResults();
            processBtn.disabled = true;

            progressBar.style.display = "block";
            progressFill.classList.remove("indeterminate");
            progressFill.style.width = "0%";
            progressText.textContent = "上传中... 0%";

            const formData = cfg.buildFormData(selectedFile);
            const xhr = new XMLHttpRequest();
            let uploadFinished = false;
            let serverResult = null;

            function tryFinish() {
                if (!uploadFinished || !serverResult) return;
                showResult(serverResult.data, serverResult.status);
            }

            xhr.upload.addEventListener("progress", e => {
                if (e.lengthComputable) {
                    const pct = Math.round((e.loaded / e.total) * 100);
                    progressFill.style.width = pct + "%";
                    progressText.textContent = "上传中... " + pct + "%";
                }
            });

            xhr.upload.addEventListener("load", () => {
                progressFill.style.width = "100%";
                progressText.textContent = "上传完成";
                setTimeout(() => {
                    uploadFinished = true;
                    if (serverResult) {
                        tryFinish();
                    } else {
                        progressFill.classList.add("indeterminate");
                        progressFill.style.width = "";
                        progressText.textContent = "服务端处理中...";
                    }
                }, 400);
            });

            xhr.addEventListener("load", () => {
                let data;
                const status = xhr.status;
                const contentType = xhr.getResponseHeader("Content-Type") || "";
                if (status === 413) {
                    showError("文件太大，请上传较小的文件");
                    return;
                }
                if (!contentType.includes("application/json")) {
                    showError("服务端返回了非预期的响应 (HTTP " + status + ")，请稍后重试");
                    return;
                }
                try {
                    data = JSON.parse(xhr.responseText);
                } catch (e) {
                    showError("解析响应失败: " + e.message);
                    return;
                }
                serverResult = { data, status };
                if (uploadFinished) {
                    tryFinish();
                }
            });

            xhr.addEventListener("error", () => {
                showError("网络错误，请检查连接后重试");
            });

            xhr.addEventListener("timeout", () => {
                showError("请求超时，请稍后重试");
            });

            xhr.timeout = 300000;

            xhr.open("POST", cfg.apiUrl);
            xhr.send(formData);
        });
    }

    // ===== 1. 奇偶页拆分 =====
    setupToolPanel({
        uploadAreaId: "uploadArea",
        fileInputId: "fileInput",
        fileInfoId: "fileInfo",
        fileNameId: "fileName",
        removeBtnId: "removeFile",
        processBtnId: "processBtn",
        progressBarId: "progressBar",
        resultCardId: "resultCard",
        resultMetaId: "resultMeta",
        resultFilesId: "resultFiles",
        errorCardId: "errorCard",
        errorTextId: "errorText",
        apiUrl: "/api/pdf/split-odd-even",
        buildFormData(file) {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("start_page", document.getElementById("startPage").value || "1");
            fd.append("end_page", document.getElementById("endPage").value || "0");
            return fd;
        },
    });

    // ===== 2. A3 转 A4 =====
    const splitDir = document.getElementById("splitDirection");
    const pageOrder = document.getElementById("pageOrder");

    splitDir.addEventListener("change", () => {
        const opts = pageOrder.options;
        if (splitDir.value === "horizontal") {
            opts[0].text = "先左后右";
            opts[0].value = "left-right";
            opts[1].text = "先右后左";
            opts[1].value = "right-left";
        } else {
            opts[0].text = "先上后下";
            opts[0].value = "top-bottom";
            opts[1].text = "先下后上";
            opts[1].value = "bottom-top";
        }
        pageOrder.selectedIndex = 0;
    });

    setupToolPanel({
        uploadAreaId: "a3UploadArea",
        fileInputId: "a3FileInput",
        fileInfoId: "a3FileInfo",
        fileNameId: "a3FileName",
        removeBtnId: "a3RemoveFile",
        processBtnId: "a3ProcessBtn",
        progressBarId: "a3ProgressBar",
        resultCardId: "a3ResultCard",
        resultMetaId: "a3ResultMeta",
        resultFilesId: "a3ResultFiles",
        errorCardId: "a3ErrorCard",
        errorTextId: "a3ErrorText",
        apiUrl: "/api/pdf/a3-to-a4",
        buildFormData(file) {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("split_direction", splitDir.value);
            fd.append("page_order", pageOrder.value);
            fd.append("start_page", document.getElementById("a3StartPage").value || "1");
            fd.append("end_page", document.getElementById("a3EndPage").value || "0");
            return fd;
        },
    });
});
