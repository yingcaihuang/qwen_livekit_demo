import { useState } from 'react'
import { Code2, Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'

type Language = 'curl' | 'python' | 'golang'

interface ApiCodeSnippetProps {
  endpoint: string
  apiKey?: string
  method?: string
  body: Record<string, unknown>
  /** Operation path appended to endpoint, e.g. "images/generations" or "responses" */
  operation: string
  /** When true, generate multipart/form-data code instead of JSON */
  multipart?: boolean
  /** Number of reference images (for multipart display) */
  referenceImageCount?: number
}

function generateCurl(url: string, apiKey: string, body: Record<string, unknown>): string {
  const bodyStr = JSON.stringify(body, null, 2)
  return `curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -H "api-key: ${apiKey}" \\
  -d '${bodyStr}'`
}

function generatePython(url: string, apiKey: string, body: Record<string, unknown>): string {
  const bodyStr = JSON.stringify(body, null, 4)
  return `import requests

url = "${url}"
headers = {
    "Content-Type": "application/json",
    "api-key": "${apiKey}",
}
payload = ${bodyStr}

response = requests.post(url, headers=headers, json=payload)
print(response.json())`
}

function generateGolang(url: string, apiKey: string, body: Record<string, unknown>): string {
  const bodyStr = JSON.stringify(body, null, 4)
  return `package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
)

func main() {
    url := "${url}"
    payload := \`${bodyStr}\`

    req, _ := http.NewRequest("POST", url, bytes.NewBufferString(payload))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("api-key", "${apiKey}")

    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    body, _ := io.ReadAll(resp.Body)
    var result map[string]interface{}
    json.Unmarshal(body, &result)
    fmt.Printf("%+v\\n", result)
}`
}

function generateCurlMultipart(url: string, apiKey: string, body: Record<string, unknown>, refCount: number): string {
  let cmd = `curl -X POST "${url}" \\\n  -H "api-key: ${apiKey}"`
  // Add form fields
  for (const [key, value] of Object.entries(body)) {
    cmd += ` \\\n  -F "${key}=${value}"`
  }
  // Add reference image placeholders
  for (let i = 0; i < refCount; i++) {
    cmd += ` \\\n  -F "image[]=@reference_image_${i + 1}.png"`
  }
  return cmd
}

function generatePythonMultipart(url: string, apiKey: string, body: Record<string, unknown>, refCount: number): string {
  const fields = Object.entries(body).map(([k, v]) => `    "${k}": (None, "${v}")`).join(',\n')
  const files = Array.from({ length: refCount }, (_, i) =>
    `    ("image[]", ("reference_${i + 1}.png", open("reference_image_${i + 1}.png", "rb"), "image/png"))`
  ).join(',\n')

  return `import requests

url = "${url}"
headers = {"api-key": "${apiKey}"}

# 表单字段
fields = {
${fields},
}

# 参考图文件（替换为实际文件路径）
files = [
${files},
]

response = requests.post(url, headers=headers, files=list(fields.items()) + files)
print(response.json())`
}

function generateGolangMultipart(url: string, apiKey: string, body: Record<string, unknown>, refCount: number): string {
  const fieldLines = Object.entries(body).map(([k, v]) => `    writer.WriteField("${k}", "${v}")`).join('\n')
  const fileLines = Array.from({ length: refCount }, (_, i) =>
    `    // 添加参考图 ${i + 1}\n    part${i + 1}, _ := writer.CreateFormFile("image[]", "reference_${i + 1}.png")\n    file${i + 1}, _ := os.Open("reference_image_${i + 1}.png")\n    io.Copy(part${i + 1}, file${i + 1})\n    file${i + 1}.Close()`
  ).join('\n')

  return `package main

import (
    "bytes"
    "fmt"
    "io"
    "mime/multipart"
    "net/http"
    "os"
)

func main() {
    url := "${url}"

    var body bytes.Buffer
    writer := multipart.NewWriter(&body)

    // 表单字段
${fieldLines}

    // 参考图文件（替换为实际文件路径）
${fileLines}

    writer.Close()

    req, _ := http.NewRequest("POST", url, &body)
    req.Header.Set("Content-Type", writer.FormDataContentType())
    req.Header.Set("api-key", "${apiKey}")

    resp, err := (&http.Client{}).Do(req)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    result, _ := io.ReadAll(resp.Body)
    fmt.Println(string(result))
}`
}

const LANGUAGES: { value: Language; label: string }[] = [
  { value: 'curl', label: 'cURL' },
  { value: 'python', label: 'Python' },
  { value: 'golang', label: 'Go' },
]

export function ApiCodeSnippet({ endpoint, apiKey, body, operation, multipart, referenceImageCount }: ApiCodeSnippetProps) {
  const [lang, setLang] = useState<Language>('curl')
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  // Resolve URL: if endpoint already contains /openai/v1, just append operation;
  // otherwise append /openai/v1/{operation}
  const base = endpoint.replace(/\/$/, '')
  const v1Marker = '/openai/v1'
  const fullUrl = base.includes(v1Marker)
    ? `${base.substring(0, base.indexOf(v1Marker) + v1Marker.length)}/${operation}`
    : `${base}${v1Marker}/${operation}`
  const key = apiKey || 'YOUR_API_KEY'

  const refCount = referenceImageCount || 0
  const generators: Record<Language, () => string> = multipart
    ? {
        curl: () => generateCurlMultipart(fullUrl, key, body, refCount),
        python: () => generatePythonMultipart(fullUrl, key, body, refCount),
        golang: () => generateGolangMultipart(fullUrl, key, body, refCount),
      }
    : {
        curl: () => generateCurl(fullUrl, key, body),
        python: () => generatePython(fullUrl, key, body),
        golang: () => generateGolang(fullUrl, key, body),
      }

  const code = generators[lang]()

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!expanded) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => setExpanded(true)}
        className="gap-1.5 text-xs"
      >
        <Code2 className="h-3.5 w-3.5" />
        查看 API 请求
      </Button>
    )
  }

  return (
    <div className="rounded-lg border bg-muted/30">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex gap-1">
          {LANGUAGES.map((l) => (
            <button
              key={l.value}
              onClick={() => setLang(l.value)}
              className={`rounded px-2 py-1 text-xs font-medium transition ${
                lang === l.value
                  ? 'bg-indigo-600 text-white'
                  : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={handleCopy} className="h-7 gap-1 text-xs">
            {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
            {copied ? '已复制' : '复制'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setExpanded(false)} className="h-7 text-xs">
            收起
          </Button>
        </div>
      </div>
      <pre className="max-h-80 overflow-auto p-3 text-xs leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  )
}
