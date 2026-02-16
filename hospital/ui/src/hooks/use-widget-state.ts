import { create } from "zustand";

interface WidgetState {
  isOpen: boolean;
  isMinimized: boolean;
  setIsOpen: (open: boolean) => void;
  setIsMinimized: (minimized: boolean) => void;
  toggleOpen: () => void;
}

export const useWidgetState = create<WidgetState>((set) => ({
  isOpen: false,
  isMinimized: false,
  setIsOpen: (isOpen) => set({ isOpen }),
  setIsMinimized: (isMinimized) => set({ isMinimized }),
  toggleOpen: () => set((s) => ({ isOpen: !s.isOpen, isMinimized: false })),
}));
