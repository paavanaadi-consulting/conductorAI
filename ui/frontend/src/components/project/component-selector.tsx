"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { COMPONENTS, type ComponentSelection } from "@/lib/types";

interface Props {
  value: ComponentSelection[];
  onChange: (val: ComponentSelection[]) => void;
}

const PHASE_COLORS: Record<string, string> = {
  DEVELOPMENT: "bg-blue-100 text-blue-800",
  DEVOPS: "bg-amber-100 text-amber-800",
  MONITORING: "bg-green-100 text-green-800",
};

export function ComponentSelector({ value, onChange }: Props) {
  const toggle = (id: ComponentSelection) => {
    onChange(
      value.includes(id)
        ? value.filter((v) => v !== id)
        : [...value, id]
    );
  };

  const grouped: Record<string, typeof COMPONENTS> = {};
  for (const c of COMPONENTS) {
    (grouped[c.phase] ??= []).push(c);
  }

  return (
    <div className="space-y-4">
      <Label className="text-sm font-medium">Components to Generate</Label>
      {Object.entries(grouped).map(([phase, items]) => (
        <div key={phase} className="space-y-2">
          <Badge variant="outline" className={PHASE_COLORS[phase] || ""}>
            {phase}
          </Badge>
          <div className="ml-2 space-y-2">
            {items?.map((comp) => (
              <div key={comp.id} className="flex items-start gap-3">
                <Checkbox
                  id={comp.id}
                  checked={value.includes(comp.id)}
                  onCheckedChange={() => toggle(comp.id)}
                />
                <div className="grid gap-0.5 leading-none">
                  <Label htmlFor={comp.id} className="cursor-pointer font-medium">
                    {comp.label}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {comp.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
