//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportMarginCall.h"
//+------------------------------------------------------------------+
//| Margin Call Report                                               |
//+------------------------------------------------------------------+
BOOL CReportMarginCall::GenerateHTML(const ReportParams* params)
  {
   MarginLevel      *levels=NULL;
   int               total =0;
   int               i,j,total_count=0,result=TRUE;
   double            total_balance=0.0,total_credit=0.0,total_profit=0.0,total_equity=0.0;
   double            total_margin =0.0,total_free  =0.0,total_add   =0.0;
   __int64           total_volume=0;
   double            add_margin=0.0;
   const UserRecord *user =NULL;
   const ConGroup   *group=NULL;
   char              tmp[256]="";
//--- checks
   if(params==NULL || params->buffer==NULL || params->buffer_size<=0) return(FALSE);
//--- generation
   levels=(MarginLevel*)params->buffer;
   if((total=params->buffer_size/sizeof(levels[0]))<=0) return(FALSE);
   if((m_file=fopen(params->filepath,"wt"))==NULL)      return(FALSE);
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
   fprintf(m_file,"<tr><td colspan=12><font size=2><b>Margin Call Report</b> ");
   FormatDateTime(time(NULL),tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file,"%s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left>Login</td><td align=left>Name</td><td>Balance</td><td>Credit</td><td>Volume</td>"
                  "<td nowrap>Floating P/L</td><td>Equity</td><td>Margin</td><td nowrap>Free Margin</td>"
                  "<td nowrap>Margin Limits</td><td nowrap>Margin Level</td><td nowrap>Add. Margin</td>");
   fprintf(m_file,"</tr>\n");
//--- for each login
   for(i=0;i<params->group.total;i++)
     {
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
      //--- find margin level
      for(j=0;j<total;j++)
        {
         if(levels[j].login!=params->group_logins[i]) continue;
         //---
         if(levels[j].level_type              <=MARGINLEVEL_OK) break;
         if((user=UserRecordGet(params,levels[j].login))==NULL) continue;
         if((group=GroupGet(params,levels[j].group))    ==NULL) continue;
         //--- background color
         if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
         else                   fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
         total_count++;
         //--- row
         fprintf(m_file,"<td align=left>%d</td>",levels[j].login);
         fprintf(m_file,"<td align=left nowrap>%s</td>",user->name);
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(user->balance,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(user->credit ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(levels[j].volume/100.0,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(levels[j].equity-levels[j].balance,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(levels[j].equity,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(levels[j].margin,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(levels[j].margin_free,2,tmp,sizeof(tmp)-1));
         if(group->margin_type==MARGIN_TYPE_PERCENT)
           {
            fprintf(m_file,"<td>%d/%d%%</td>",group->margin_call,group->margin_stopout);
            fprintf(m_file,"<td style=mso-number-format:0\\.00%%;>%.2lf%%</td>",levels[j].margin_level);
            add_margin=group->margin_call*levels[j].margin/100.0-levels[j].equity;
           }
         else  // MARGIN_TYPE_CURRENCY
           {
            fprintf(m_file,"<td>%d/%d$</td>",group->margin_call,group->margin_stopout);
            fprintf(m_file,"<td style=mso-number-format:0\\.00$;>%.2lf$</td>",levels[j].margin_level);
            add_margin=group->margin_call-levels[j].equity;
           }
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(add_margin,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"</tr>\n");
         //--- total
         total_balance+=user->balance;
         total_credit +=user->credit;
         total_profit +=(levels[j].equity-levels[j].balance);
         total_equity +=levels[j].equity;
         total_margin +=levels[j].margin;
         total_free   +=levels[j].margin_free;
         total_volume +=levels[j].volume;
         total_add    +=add_margin;
         //---
         break;
        }
     }
//--- total
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right><td colspan=2 align=left><b>Total:</b></td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_balance,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_credit ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_volume/100.0,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_profit,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_equity,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_margin,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_free  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money colspan=3><b>%s</b></td>",ToMoney(total_add,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</tr>\n</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportMarginCall::GenerateCSV(const ReportParams* params)
  {
   MarginLevel      *levels=NULL;
   int               total =0;
   int               i,j,total_count=0,result=TRUE;
   double            total_balance=0.0,total_credit=0.0,total_profit=0.0,total_equity=0.0;
   double            total_margin =0.0,total_free  =0.0,total_add   =0.0;
   __int64           total_volume=0;
   double            add_margin=0.0;
   const UserRecord *user =NULL;
   const ConGroup   *group=NULL;
   char              tmp[256]="";
//--- checks
   if(params==NULL || params->buffer==NULL)             return(FALSE);
//--- generation
   levels=(MarginLevel*)params->buffer;
   if((total=params->buffer_size/sizeof(levels[0]))<=0) return(FALSE);
   if((m_file=fopen(params->filepath,"wt"))==NULL)      return(FALSE);
//--- report header
   fprintf(m_file,"Margin Call Report ");
   FormatDateTime(time(NULL),tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file,"%s\n",tmp);
//---
   fprintf(m_file,"Login;Name;Balance;Credit;Volume;Floating P/L;Equity;Margin;"
                  "Free Margin;Margin Limits;Margin Level;Add. Margin\n");
//--- for each login
   for(i=0; i<params->group.total; i++)
     {
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
      //--- find margin level
      for(j=0; j<total; j++)
        {
         if(levels[j].login!=params->group_logins[i]) continue;
         //---
         if(levels[j].level_type              <=MARGINLEVEL_OK) break;
         if((user=UserRecordGet(params,levels[j].login))==NULL) continue;
         if((group=GroupGet(params,levels[j].group))    ==NULL) continue;
         total_count++;
         //--- row
         fprintf(m_file,"%d;",levels[j].login);
         fprintf(m_file,"%s;",user->name);
         fprintf(m_file,"%.2lf;",user->balance);
         fprintf(m_file,"%.2lf;",user->credit);
         fprintf(m_file,"%.2lf;",levels[j].volume/100.0);
         fprintf(m_file,"%.2lf;",levels[j].equity-levels[j].balance);
         fprintf(m_file,"%.2lf;",levels[j].equity);
         fprintf(m_file,"%.2lf;",levels[j].margin);
         fprintf(m_file,"%.2lf;",levels[j].margin_free);
         if(group->margin_type==MARGIN_TYPE_PERCENT)
           {
            fprintf(m_file,"%d/%d%%;",group->margin_call,group->margin_stopout);
            fprintf(m_file,"%.2lf%%;",levels[j].margin_level);
            add_margin=group->margin_call*levels[j].margin/100.0-levels[j].equity;
           }
         else  // MARGIN_TYPE_CURRENCY
           {
            fprintf(m_file,"%d/%d$;",group->margin_call,group->margin_stopout);
            fprintf(m_file,"%.2lf$;",levels[j].margin_level);
            add_margin=group->margin_call-levels[j].equity;
           }
         fprintf(m_file,"%.2lf\n",add_margin);
         //--- total
         total_balance+=user->balance;
         total_credit +=user->credit;
         total_profit +=(levels[j].equity-levels[j].balance);
         total_equity +=levels[j].equity;
         total_margin +=levels[j].margin;
         total_free   +=levels[j].margin_free;
         total_volume +=levels[j].volume;
         total_add    +=add_margin;
         //---
        }
     }
//--- total
   fprintf(m_file,";Total:;");
   fprintf(m_file,"%.2lf;",total_balance);
   fprintf(m_file,"%.2lf;",total_credit);
   fprintf(m_file,"%.2lf;",total_volume/100.0);
   fprintf(m_file,"%.2lf;",total_profit);
   fprintf(m_file,"%.2lf;",total_equity);
   fprintf(m_file,"%.2lf;",total_margin);
   fprintf(m_file,"%.2lf;",total_free);
   fprintf(m_file,";;");
   fprintf(m_file,"%.2lf\n",total_add);
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
