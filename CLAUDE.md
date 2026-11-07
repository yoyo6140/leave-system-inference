# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

`leave-system-inference` 是請假系統第二階段（AI 助理）的推論服務，部署在 Modal。這個 repo 無狀態、不連資料庫；向量與對話紀錄的讀寫都由後端 `leave-system-backend` 負責，這裡只負責提供模型推論的 API。

目前只做 embedding 模型（`intfloat/multilingual-e5-large-instruct`），對話模型（Gemma 4）之後再加。

完整規格見 `leave-system-backend` 的 `doc/spec/ai-service.md`。

## 常用指令

```bash
pip install modal
modal setup                  # 首次使用需登入授權

modal serve <app 檔案>        # 本機開發用，會給一個暫時的 URL
modal deploy <app 檔案>       # 正式部署
```

## 規則
本專案用於練習架設模型，所以必須實際操作，除非開發人員直接下指令，不然禁止自行新增檔案、修改檔案(docs資料夾內檔案除外)
commit與push 由開發人員自己操作
AI僅提供簡短commit msg
任何檔案的新增、修改均先提出如何施作，禁止在開發人員未同意下，自行新增、修改
當開發人員詢問commit msg 就要在docs資料夾內，新增或修改檔案，將開發所下的指令或者是操作紀錄下。

