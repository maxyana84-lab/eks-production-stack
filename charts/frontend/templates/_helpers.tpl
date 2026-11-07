{{- define "app.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "app.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "app.labels" -}}
{{ include "app.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: eks-production-stack
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/* nodeAffinity from values: "preferred" (soft) or "required" (hard) */}}
{{- define "app.affinity" -}}
{{- if .Values.nodeAffinity.enabled }}
affinity:
  nodeAffinity:
    {{- if eq .Values.nodeAffinity.type "required" }}
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: {{ .Values.nodeAffinity.key }}
              operator: In
              values: {{ toYaml .Values.nodeAffinity.values | nindent 16 }}
    {{- else }}
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: {{ .Values.nodeAffinity.weight | default 100 }}
        preference:
          matchExpressions:
            - key: {{ .Values.nodeAffinity.key }}
              operator: In
              values: {{ toYaml .Values.nodeAffinity.values | nindent 16 }}
    {{- end }}
{{- end }}
{{- end -}}
