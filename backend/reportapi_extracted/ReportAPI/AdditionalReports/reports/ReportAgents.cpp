//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportAgents.h"
//+------------------------------------------------------------------+
//| Agents Report                                                    |
//+------------------------------------------------------------------+
BOOL CReportAgents::GenerateHTML(const ReportParams* params)
  {
   char              tmp[256]="",num_fmt[32]="";
   int               agents[4096];
   int               agents_total=0;
   int               i,j,total_count=0,result=TRUE;
   double            commagent_total;
   const UserRecord *ur=NULL;
   UserRecord        user={0};
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
//--- fill agent accounts
   memset(agents,0,sizeof(agents));
   for(i=0;i<params->group.total;i++)
     {
      //--- user with agent?
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL || ur->agent_account<=0) continue;
      //--- agent already in the list?
      for(j=0; j<agents_total; j++)
         if(agents[j]==ur->agent_account) break;
      if(j<agents_total) continue;  // already in the list
      //--- add agent to the list
      agents[agents_total++]=ur->agent_account;
      //--- check for free space in agents array
      if(agents_total>=sizeof(agents)/sizeof(agents[0])) break;
     }
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=\"99%%\">\n");
   fprintf(m_file,"<tr><td colspan=15><font size=2><b>Agents Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left>Deal</td><td align=left>Login</td><td nowrap>Open Time</td><td>Type</td><td>Item</td><td>Volume</td>"
                  "<td nowrap>Open Price</td><td>S/L</td><td>T/P</td><td nowrap>Close Time</td><td nowrap>Close Price</td>"
                  "<td nowrap>Agent Commission</td><td>Commission</td><td>Storage</td><td>Profit</td>");
   fprintf(m_file,"</tr>\n");
//--- for each agent
   for(j=0;j<agents_total;j++)
     {
      //--- report agent trades
      commagent_total=0.0;
      TradeRecord *record=params->trades;
      for(i=0;i<params->trades_total;i++,record++)
        {
         if(record->cmd>OP_SELL) continue;  // only closed trades
         //--- check agent account
         if((ur=UserRecordGet(params, record->login))==NULL) continue;
         if(ur->agent_account!=agents[j])                    continue;
         //--- background color
         if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
         else                   fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
         total_count+=1;
         //--- price format
         if(record->digits<0 || record->digits>8) { COPY_STR(num_fmt,"class=pt4") }
         else StringCchPrintfA(num_fmt,sizeof(num_fmt)-1,"class=pt%d",record->digits);
         //--- row
         fprintf(m_file,"<td align=left>%d</td>",record->order);
         fprintf(m_file,"<td align=left>%d</td>",record->login);
         fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(record->open_time,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap>%s</td>",GetCmd(record->cmd));
         strcpy(tmp,record->symbol); _strlwr(tmp);
         fprintf(m_file,"<td nowrap>%s</td>",tmp);
         fprintf(m_file,"<td nowrap>%s</td>",ToVolume(record->volume/100.0,tmp,sizeof(tmp)-1));
         ToSymExt(tmp,record->open_price,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         ToSym(tmp,sizeof(tmp)-1,record->sl,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         ToSym(tmp,sizeof(tmp)-1,record->tp,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(record->close_time,tmp,sizeof(tmp)-1));
         ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->commission_agent,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->commission,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->storage,2,tmp,sizeof(tmp)-1));
         if(record->profit!=0.00)
            fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->profit,2,tmp,sizeof(tmp)-1));
         else
            fprintf(m_file,"<td>&nbsp;</td>");
         fprintf(m_file,"</tr>\n");
         //--- total
         commagent_total=NormalizeDouble(commagent_total+record->commission_agent,2);
        }
      //--- agent info
      if((ur=UserRecordGet(params,agents[j]))==NULL)
        {
         memset(&user,0,sizeof(user));
         user.login=agents[j];
         ur=&user;
        }
      fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=left>");
      fprintf(m_file,"<td>&nbsp;</td><td align=right>%d</td>",ur->login);
      fprintf(m_file,"<td colspan=3 nowrap >%s</td>",ur->name);
      fprintf(m_file,"<td colspan=2 align=right>Balance:</td>");
      fprintf(m_file,"<td colspan=2 align=right nowrap class=money>%s</td>",ToMoney(ur->balance,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td colspan=2 align=right nowrap>Agent commission:</td>");
      fprintf(m_file,"<td align=right nowrap class=money>%s</td>",ToMoney(commagent_total,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td colspan=3>&nbsp;</td></tr>\n");
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,j,agents_total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
//---
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportAgents::GenerateCSV(const ReportParams* params)
  {
   char              tmp[256]="";
   int               agents[4096];
   int               agents_total=0;
   int               i,j,total_count=0,result=TRUE;
   double            commagent_total;
   const UserRecord *ur=NULL;
   UserRecord        user={0};
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- fill agent accounts
   memset(agents,0,sizeof(agents));
   for(i=0; i<params->group.total; i++)
     {
      //--- user with agent?
      if((ur=UserRecordGet(params, params->group_logins[i]))==NULL || ur->agent_account<=0) continue;
      //--- agent already in the list?
      for(j=0; j<agents_total; j++)
         if(agents[j]==ur->agent_account) break;
      if(j<agents_total) continue;  // already in the list
      //--- add agent to the list
      agents[agents_total++]=ur->agent_account;
      //--- check for free space in agents array
      if(agents_total>=sizeof(agents)/sizeof(agents[0])) break;
     }
//--- report header
   fprintf(m_file,"Agents Report for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
   fprintf(m_file,"Deal;Login;Open Time;Type;Item;Volume;Open Price;S/L;T/P;Close Time;Close Price"
                  "Agent Commission;Commission;Storage;Profit\n");
//--- for each agent
   for(j=0;j<agents_total;j++)
     {
      //--- report agent trades
      commagent_total=0.0;
      TradeRecord *record=params->trades;
      for(i=0;i<params->trades_total;i++,record++)
        {
         if(record->cmd>OP_SELL) continue;  // only closed trades
         //--- check agent account
         if((ur=UserRecordGet(params, record->login))==NULL) continue;
         if(ur->agent_account!=agents[j])                    continue;
         total_count++;
         //--- row
         fprintf(m_file,"%d;",record->order);
         fprintf(m_file,"%d;",record->login);
         FormatDateTime(record->open_time,tmp,sizeof(tmp)-1);
         fprintf(m_file,"%s;",tmp);
         fprintf(m_file,"%s;",GetCmd(record->cmd));
         strcpy(tmp,record->symbol); _strlwr(tmp);
         fprintf(m_file,"%s;",tmp);
         fprintf(m_file,"%.2lf;",record->volume/100.0);
         ToSymExt(tmp,record->open_price,record->digits);
         fprintf(m_file,"%s;",tmp);
         ToSym(tmp,sizeof(tmp)-1,record->sl,record->digits);
         fprintf(m_file,"%s;",tmp);
         ToSym(tmp,sizeof(tmp)-1,record->tp,record->digits);
         fprintf(m_file,"%s;",tmp);
         FormatDateTime(record->close_time,tmp,sizeof(tmp)-1);
         fprintf(m_file,"%s;",tmp);
         ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
         fprintf(m_file,"%s;",tmp);
         fprintf(m_file,"%.2lf;",record->commission_agent);
         fprintf(m_file,"%.2lf;",record->commission);
         fprintf(m_file,"%.2lf;",record->storage);
         if(record->profit!=0.00)
            fprintf(m_file,"%.2lf;",record->profit);
         else
            fprintf(m_file,";");
         fprintf(m_file,"\n");
         //--- total
         commagent_total=NormalizeDouble(commagent_total+record->commission_agent,2);
        }
      //--- agent info
      if((ur=UserRecordGet(params,agents[j]))==NULL)
        {
         memset(&user,0,sizeof(user));
         user.login=agents[j];
         ur=&user;
        }
      fprintf(m_file,";%d;",ur->login);
      fprintf(m_file,"%s;;;",ur->name);
      fprintf(m_file,";Balance:;</td>");
      fprintf(m_file,";%.2lf;",ur->balance);
      fprintf(m_file,";Agent commission:;");
      fprintf(m_file,"%.2lf;;\n",commagent_total);
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,j,agents_total)!=0)
           {
            result=FALSE; break;
           }
     }
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
