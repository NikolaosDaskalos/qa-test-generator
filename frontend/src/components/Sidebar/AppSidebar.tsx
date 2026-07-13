import { Bot } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import { type Item, Main } from "./Main"
import { RepositoryPanel } from "./RepositoryPanel"
import { User } from "./User"

const baseItems: Item[] = [{ icon: Bot, title: "Copilot", path: "/" }]

export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={baseItems} />
        <RepositoryPanel />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
