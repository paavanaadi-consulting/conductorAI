"use client";

import { useCallback, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Upload, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { templatesApi, uploadYaml } from "@/lib/api";

interface Props {
  label: string;
  category: "requirements" | "infrastructure";
  value: string;
  onChange: (yaml: string) => void;
}

export function YamlUpload({ label, category, value, onChange }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [filename, setFilename] = useState<string>();
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: templates } = useQuery({
    queryKey: ["templates", category],
    queryFn: () =>
      category === "requirements"
        ? templatesApi.listRequirements()
        : templatesApi.listInfrastructure(),
  });

  const handleFile = useCallback(
    async (file: File) => {
      const result = await uploadYaml(file);
      setFilename(result.filename);
      onChange(result.content);
    },
    [onChange]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onSelectTemplate = async (val: string | null) => {
    if (!val) return;
    const data = await templatesApi.getContent(category, val);
    setFilename(val);
    onChange(data.content);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">{label}</Label>
        {templates && templates.length > 0 && (
          <Select onValueChange={onSelectTemplate}>
            <SelectTrigger className="w-48 h-8 text-xs">
              <SelectValue placeholder="Use template..." />
            </SelectTrigger>
            <SelectContent>
              {templates.map((t) => (
                <SelectItem key={t.filename} value={t.filename}>
                  {t.filename.replace(/\.ya?ml$/, "")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50"
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".yaml,.yml"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
        {filename ? (
          <div className="flex items-center justify-center gap-2 text-sm">
            <FileText className="h-4 w-4 text-primary" />
            <span className="font-medium">{filename}</span>
          </div>
        ) : (
          <div className="space-y-1">
            <Upload className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Drop a YAML file or click to browse
            </p>
          </div>
        )}
      </div>

      {/* YAML preview / editor */}
      {value && (
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={10}
          className="font-mono text-xs"
          placeholder="YAML content..."
        />
      )}
    </div>
  );
}
