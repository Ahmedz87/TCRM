//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportDetailedCommissions.h"
//+------------------------------------------------------------------+
//| Detailed Commission Report                                       |
//+------------------------------------------------------------------+
BOOL CReportDetailedCommissions::GenerateHTML(const ReportParams* params)
  {
   char    tmp[256]="";
   int     i,j,isec,total_count=0,result=TRUE;
   double  total_comm=.0,total_agent=.0,comm=.0,agent=.0;
   __int64 total_lots=0,lots=0,slots[MAX_SEC_GROUPS];
   const   UserRecord *ur =NULL;
   const   ConSymbol  *sec=NULL;
   const   ConGroup   *grp=NULL;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- body
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".lots  { mso-number-format:0\\.00; }\n"
                  ".dt    { mso-number-format:\"yyyy\\.mm\\.dd hh\\:mm\"; }\n"
                  ".pt0   { mso-number-format:0; }\n"
                  ".pt1   { mso-number-format:0\\.0; }\n"
                  ".pt2   { mso-number-format:0\\.00; }\n"
                  ".pt3   { mso-number-format:0\\.000; }\n"
                  ".pt4   { mso-number-format:0\\.0000; }\n"
                  ".pt5   { mso-number-format:0\\.00000; }\n"
                  ".pt6   { mso-number-format:0\\.000000; }\n"
                  ".pt7   { mso-number-format:0\\.0000000; }\n"
                  ".pt8   { mso-number-format:0\\.00000000; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=\"99%%\">\n");
   fprintf(m_file,"<tr><td colspan=6><font size=2><b>Commissions Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left>Login</td><td align=left>Name</td><td nowrap>Closed Volume</td>"
               "<td>Commissions</td><td>Total</td><td nowrap>Agent Commission</td>");
   fprintf(m_file,"</tr>\n");
//--- for each login
   for(i=0;i<params->group.total;i++)
     {
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL) continue;
      //---
      lots=0; comm=agent=.0;
      memset(slots,0,MAX_SEC_GROUPS*sizeof(slots[0]));
      //--- collect data
      for(j=0; j<params->trades_total; j++)
        {
         if(params->trades[j].login!=params->group_logins[i]) continue;
         if(params->trades[j].cmd<=OP_SELL)
           {
            lots +=params->trades[j].volume;
            comm +=params->trades[j].commission;
            agent+=params->trades[j].commission_agent;
            //---
            if((sec=SymbolGet(params,params->trades[j].symbol))==NULL) continue;
            slots[sec->type]+=params->trades[j].volume;
           }
        }
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=right valign=top>");
      else                   fprintf(m_file,"<tr align=right valign=top bgcolor=\"#e0e0e0\">");
      //--- row
      fprintf(m_file,"<td align=left>%d</td>",params->group_logins[i]);
      fprintf(m_file,"<td nowrap align=left>%s</td>",ur->name);
      fprintf(m_file,"<td nowrap>%s</td>",ToVolume(lots/100.0,tmp,sizeof(tmp)-1));
      //--- commissions
      fprintf(m_file,"<td nowrap>");
      if((grp=GroupGet(params,ur->group))!=NULL)
        {
         for(isec=0; isec<MAX_SEC_GROUPS; isec++)
           {
            fprintf(m_file,"%.2lf x %.2lf",slots[isec]/100.0,grp->secgroups[isec].comm_base);
            if((isec+1)%8==0) fprintf(m_file,"<br>");
            else              fprintf(m_file,", ");
           }
        }
      fprintf(m_file,"</td>");
      //--- commissions
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(comm ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(agent,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"</tr>\n");
      //--- totals
      total_lots +=lots;
      total_comm +=comm;
      total_agent+=agent;
      total_count++;
      //--- details
      for(isec=0;isec<params->symbols_total;isec++)
        {
         sec=&params->symbols[isec];
         lots=0; comm=agent=.0;
         for(j=0;j<params->trades_total;j++)
           {
            if(params->trades[j].login!=params->group_logins[i]) continue;
            if(params->trades[j].cmd>OP_SELL)                    continue;
            if(strcmp(params->trades[j].symbol,sec->symbol)!=0)  continue;
            //---
            lots +=params->trades[j].volume;
            comm +=params->trades[j].commission;
            agent+=params->trades[j].commission_agent;
           }
         if(lots<1) continue;
         //---
         if((total_count&1)==0) fprintf(m_file,"<tr align=right valign=top bgcolor=\"#e0e0e0\">");
         else                   fprintf(m_file,"<tr align=right valign=top>");
         //---
         fprintf(m_file,"<td>&nbsp;</td>");
         fprintf(m_file,"<td align=right nowrap>%s</td>",sec->symbol);
         fprintf(m_file,"<td nowrap>%s</td><td>&nbsp;</td>",ToVolume(lots/100.0,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(comm ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(agent,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"</tr>\n");
        }
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
//--- total
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td colspan=2 align=left><b>Total:</b></td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_lots/100.0,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td>&nbsp;</td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_comm ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_agent,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</tr>\n</table>\n</div>\n</body></html>\n");
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportDetailedCommissions::GenerateCSV(const ReportParams* params)
  {
   char    tmp[256]="";
   int     i,j,isec,total_count=0,result=TRUE;
   double  total_comm=.0,total_agent=.0,comm=.0,agent=.0;
   __int64 total_lots=0,lots=0,slots[MAX_SEC_GROUPS];
   const   UserRecord *ur =NULL;
   const   ConSymbol  *sec=NULL;
   const   ConGroup   *grp=NULL;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- report header
   fprintf(m_file,"Detailed Commissions Report for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
   fprintf(m_file,"Login;Name;Closed Volume;Commissions;Total;Agent Commission\n");
//--- for each login
   for(i=0;i<params->group.total;i++)
     {
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL) continue;
      //---
      lots=0; comm=agent=.0;
      memset(slots,0,MAX_SEC_GROUPS*sizeof(slots[0]));
      //--- collect data
      for(j=0;j<params->trades_total;j++)
        {
         if(params->trades[j].login!=params->group_logins[i]) continue;
         if(params->trades[j].cmd<=OP_SELL)
           {
            lots +=params->trades[j].volume;
            comm +=params->trades[j].commission;
            agent+=params->trades[j].commission_agent;
            //---
            if((sec=SymbolGet(params,params->trades[j].symbol))==NULL) continue;
            slots[sec->type]+=params->trades[j].volume;
           }
        }
      //--- row
      fprintf(m_file,"%d;",params->group_logins[i]);
      fprintf(m_file,"%s;",ur->name);
      fprintf(m_file,"%.2lf;",lots/100.0);
      //--- commissions
      if((grp=GroupGet(params,ur->group))!=NULL)
        {
         for(isec=0;isec<MAX_SEC_GROUPS;isec++)
           {
            fprintf(m_file,"%.2lf x %.2lf",slots[isec]/100.0,grp->secgroups[isec].comm_base);
            if((isec+1)<MAX_SEC_GROUPS) fprintf(m_file," / ");
           }
        }
      fprintf(m_file,";");
      //--- commissions
      fprintf(m_file,"%.2lf;",comm);
      fprintf(m_file,"%.2lf\n",agent);
      //--- totals
      total_lots +=lots;
      total_comm +=comm;
      total_agent+=agent;
      total_count++;
      //--- details
      for(isec=0; isec<params->symbols_total; isec++)
        {
         sec=&params->symbols[isec];
         lots=0; agent=0; comm=0;
         for(j=0;j<params->trades_total;j++)
           {
            if(params->trades[j].login!=params->group_logins[i]) continue;
            if(params->trades[j].cmd>OP_SELL)                    continue;
            if(strcmp(params->trades[j].symbol,sec->symbol)!=0)  continue;
            //---
            lots +=params->trades[j].volume;
            comm +=params->trades[j].commission;
            agent+=params->trades[j].commission_agent;
           }
         if(lots<1) continue;
         //---
         fprintf(m_file,";%s;",sec->symbol);
         fprintf(m_file,"%.2lf;;",lots/100.0);
         fprintf(m_file,"%.2lf;",comm);
         fprintf(m_file,"%.2lf\n",agent);
        }
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress!=NULL && params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
//--- total
   fprintf(m_file,";Total:;");
   fprintf(m_file,"%.2lf;;",total_lots/100.0);
   fprintf(m_file,"%.2lf;", total_comm);
   fprintf(m_file,"%.2lf\n",total_agent);
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
