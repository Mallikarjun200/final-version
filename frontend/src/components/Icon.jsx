import {
  ArrowRight, Bell, BookOpen, Building2, CalendarClock, CalendarDays, ChevronDown, Download,
  ChevronRight, CreditCard, FileBarChart, FileSpreadsheet, FileText, FlaskConical,
  House, Landmark, ListTree, Menu, Percent, PencilLine, PiggyBank, Scale, Search,
  TrendingUp, X,
} from 'lucide-react'

const ICONS = {
  ArrowRight, Bell, BookOpen, Building2, CalendarClock, CalendarDays, ChevronDown, Download,
  ChevronRight, CreditCard, FileBarChart, FileSpreadsheet, FileText, FlaskConical,
  House, Landmark, ListTree, Menu, Percent, PencilLine, PiggyBank, Scale, Search,
  TrendingUp, X,
}

export default function Icon({ name, size = 18, strokeWidth = 1.9, ...rest }) {
  const Cmp = ICONS[name]
  if (!Cmp) return null
  return <Cmp size={size} strokeWidth={strokeWidth} aria-hidden="true" {...rest} />
}
