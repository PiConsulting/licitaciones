import { ReactNode, useState } from "react";

export interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultTab?: string;
  onChange?: (tabId: string) => void;
}

export function Tabs({ tabs, defaultTab, onChange }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab ?? tabs[0]?.id);

  const handleTabClick = (tabId: string) => {
    setActiveTab(tabId);
    onChange?.(tabId);
  };

  const activeTabContent = tabs.find((tab) => tab.id === activeTab)?.content;

  return (
    <div className="tabs-container">
      <div>
        <nav className="flex flex-wrap gap-2" aria-label="Tabs">
          {tabs.map((tab) => {
            const isActive = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => handleTabClick(tab.id)}
                className={`
                  whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition-colors
                  focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cedi-electric
                  ${
                    isActive
                      ? "bg-cedi-gradient-button text-cedi-white"
                      : "border border-cedi-navy-20 text-cedi-navy-68 hover:border-cedi-navy-30 hover:text-cedi-navy"
                  }
                `}
                aria-current={isActive ? "page" : undefined}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="tab-content mt-6">{activeTabContent}</div>
    </div>
  );
}
