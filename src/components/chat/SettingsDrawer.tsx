import { useState } from 'react';
import { Settings as SettingsIcon, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerTrigger,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerClose,
} from '@/components/ui/drawer';
import { SettingsPanel } from './SettingsPanel';

export function SettingsDrawer() {
  const [open, setOpen] = useState(false);

  return (
    <Drawer open={open} onOpenChange={setOpen}>
      <DrawerTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <SettingsIcon className="h-5 w-5" />
          <span className="sr-only">Open settings</span>
        </Button>
      </DrawerTrigger>
      <DrawerContent className="max-h-[90vh]">
        <DrawerHeader className="flex items-center justify-between border-b">
          <DrawerTitle>Settings</DrawerTitle>
          <DrawerClose asChild>
            <Button
              variant="ghost"
              size="sm"
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </Button>
          </DrawerClose>
        </DrawerHeader>
        <div className="overflow-y-auto">
          <SettingsPanel />
        </div>
      </DrawerContent>
    </Drawer>
  );
}
