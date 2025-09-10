import { useChatStore } from '@/stores/chat';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function SettingsPanel() {
  const { settings, updateSettings, resetSettings } = useChatStore();

  return (
    <TooltipProvider>
      <div className="p-4 space-y-8">
        {/* Retrieval group */}
        <section className="space-y-4">
          <h2 className="text-sm font-medium">Retrieval</h2>

          {/* Top-K */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">Top-K Results</CardTitle>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="max-w-xs">
                      Number of documents to retrieve. Higher values give more
                      context but may add noise.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </div>
              <CardDescription>How many sources to search</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="topk-slider" className="text-sm">
                    Number of sources
                  </Label>
                  <span className="text-sm font-medium bg-muted px-2 py-1 rounded">
                    {settings.topK}
                  </span>
                </div>
                <Slider
                  id="topk-slider"
                  min={1}
                  max={20}
                  step={1}
                  value={[settings.topK]}
                  onValueChange={(value) => updateSettings({ topK: value[0] })}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Focused (1)</span>
                  <span>Comprehensive (20)</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* MMR */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">MMR Balance</CardTitle>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="max-w-xs">
                      Controls diversity vs. relevance in retrieval. 0 favors
                      diversity, 1 favors similarity.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </div>
              <CardDescription>Adjust Max Marginal Relevance</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="mmr-slider" className="text-sm">
                    Lambda
                  </Label>
                  <span className="text-sm font-medium bg-muted px-2 py-1 rounded">
                    {settings.mmr.toFixed(2)}
                  </span>
                </div>
                <Slider
                  id="mmr-slider"
                  min={0}
                  max={1}
                  step={0.05}
                  value={[settings.mmr]}
                  onValueChange={(value) => updateSettings({ mmr: value[0] })}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Diverse (0)</span>
                  <span>Similar (1)</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Answering group */}
        <section className="space-y-4">
          <h2 className="text-sm font-medium">Answering</h2>
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">Temperature</CardTitle>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="max-w-xs">
                      Controls randomness in answers. Lower values are more
                      deterministic.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </div>
              <CardDescription>Response creativity</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="temp-slider" className="text-sm">
                    Temperature
                  </Label>
                  <span className="text-sm font-medium bg-muted px-2 py-1 rounded">
                    {settings.temperature.toFixed(1)}
                  </span>
                </div>
                <Slider
                  id="temp-slider"
                  min={0}
                  max={2}
                  step={0.1}
                  value={[settings.temperature]}
                  onValueChange={(value) => updateSettings({ temperature: value[0] })}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Focused (0)</span>
                  <span>Creative (2)</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Display group */}
        <section className="space-y-4">
          <h2 className="text-sm font-medium">Display</h2>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base">Show images</CardTitle>
                <CardDescription>Render images in answers when available</CardDescription>
              </div>
              <Switch
                checked={settings.showImages}
                onCheckedChange={(v) => updateSettings({ showImages: v })}
                className="ml-4"
              />
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base">Compact mode</CardTitle>
                <CardDescription>Tighten message spacing</CardDescription>
              </div>
              <Switch
                checked={settings.compactMode}
                onCheckedChange={(v) => updateSettings({ compactMode: v })}
                className="ml-4"
              />
            </CardHeader>
          </Card>
        </section>

        <div className="flex justify-end pt-2">
          <Button
            variant="outline"
            onClick={resetSettings}
            className="focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Reset to defaults
          </Button>
        </div>
      </div>
    </TooltipProvider>
  );
}
