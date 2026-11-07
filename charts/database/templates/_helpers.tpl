{{- define "db.fullname" -}}
{{- default "database-postgresql" .Values.postgresql.fullnameOverride -}}
{{- end -}}

{{- define "db.labels" -}}
app.kubernetes.io/name: database
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: eks-production-stack
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
