"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import * as z from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateTrigger, useAvailableTriggerTypes } from "@/hooks/use-triggers";
import { toast } from "sonner";
import { useState } from "react";
import { Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import { useApps } from "@/hooks/use-app";
import { useLinkedAccounts } from "@/hooks/use-linked-account";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";

const formSchema = z.object({
  app_name: z.string().min(1, "Please select an app"),
  linked_account_owner_id: z.string().min(1, "Please select a linked account"),
  trigger_type: z.string().min(1, "Please select a trigger type"),
  trigger_name: z.string().min(1, "Trigger name is required"),
  description: z.string().optional(),
  config: z.record(z.any()).optional(),
});

type FormValues = z.infer<typeof formSchema>;

interface CreateTriggerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const TRIGGER_TYPES = {
  HUBSPOT: [
    {
      value: "contact.creation",
      label: "Contact Created",
      description: "When a new contact is created",
    },
    {
      value: "contact.deletion",
      label: "Contact Deleted",
      description: "When a contact is deleted",
    },
    {
      value: "contact.propertyChange",
      label: "Contact Property Changed",
      description: "When contact properties change",
    },
    {
      value: "deal.creation",
      label: "Deal Created",
      description: "When a new deal is created",
    },
    {
      value: "company.creation",
      label: "Company Created",
      description: "When a new company is created",
    },
  ],
  SHOPIFY: [
    {
      value: "orders/create",
      label: "Order Created",
      description: "When a new order is placed",
    },
    {
      value: "orders/updated",
      label: "Order Updated",
      description: "When an order is updated",
    },
    {
      value: "orders/paid",
      label: "Order Paid",
      description: "When an order payment is confirmed",
    },
    {
      value: "products/create",
      label: "Product Created",
      description: "When a new product is added",
    },
    {
      value: "products/update",
      label: "Product Updated",
      description: "When a product is modified",
    },
    {
      value: "customers/create",
      label: "Customer Created",
      description: "When a new customer signs up",
    },
  ],
  SLACK: [
    {
      value: "message.channels",
      label: "Channel Message",
      description: "When a message is posted to a channel",
    },
    {
      value: "app_mention",
      label: "App Mention",
      description: "When your app is mentioned",
    },
    {
      value: "reaction_added",
      label: "Reaction Added",
      description: "When a reaction is added to a message",
    },
    {
      value: "member_joined_channel",
      label: "Member Joined",
      description: "When someone joins a channel",
    },
    {
      value: "file_shared",
      label: "File Shared",
      description: "When a file is shared",
    },
  ],
  GITHUB: [
    {
      value: "push",
      label: "Push",
      description: "When code is pushed to a repository",
    },
    {
      value: "pull_request",
      label: "Pull Request",
      description: "When a pull request is opened/updated",
    },
    {
      value: "issues",
      label: "Issue",
      description: "When an issue is opened/closed",
    },
    {
      value: "star",
      label: "Star Added",
      description: "When a repository is starred",
    },
    {
      value: "release",
      label: "Release Published",
      description: "When a new release is published",
    },
  ],
  NOTION: [
    {
      value: "page.created",
      label: "Page Created",
      description: "When a new page is created",
    },
    {
      value: "page.content_updated",
      label: "Page Content Updated",
      description: "When page content is modified",
    },
    {
      value: "page.properties_updated",
      label: "Page Properties Updated",
      description: "When page properties change",
    },
    {
      value: "page.deleted",
      label: "Page Deleted",
      description: "When a page is deleted",
    },
    {
      value: "data_source.created",
      label: "Database Created",
      description: "When a new database is created",
    },
    {
      value: "data_source.schema_updated",
      label: "Database Schema Updated",
      description: "When database structure changes",
    },
    {
      value: "comment.created",
      label: "Comment Created",
      description: "When a new comment is added",
    },
  ],
  GOOGLE_CALENDAR: [
    {
      value: "calendar.event.created",
      label: "Event Created",
      description: "When a new calendar event is created",
    },
    {
      value: "calendar.event.updated",
      label: "Event Updated",
      description: "When a calendar event is modified",
    },
    {
      value: "calendar.event.deleted",
      label: "Event Deleted",
      description: "When a calendar event is deleted",
    },
  ],
  MICROSOFT_CALENDAR: [
    {
      value: "calendar.event.created",
      label: "Event Created",
      description: "When a new calendar event is created",
    },
    {
      value: "calendar.event.updated",
      label: "Event Updated",
      description: "When a calendar event is modified",
    },
    {
      value: "calendar.event.deleted",
      label: "Event Deleted",
      description: "When a calendar event is deleted",
    },
  ],
  GMAIL: [
    {
      value: "message.received",
      label: "Message Received",
      description: "When a new email is received",
    },
    {
      value: "message.sent",
      label: "Message Sent",
      description: "When an email is sent",
    },
    {
      value: "label.added",
      label: "Label Added",
      description: "When a label is added to a message",
    },
  ],
};

export function CreateTriggerDialog({
  open,
  onOpenChange,
}: CreateTriggerDialogProps) {
  const [step, setStep] = useState(1);
  const { mutateAsync: createTrigger, isPending } = useCreateTrigger();
  const { data: apps, isPending: appsLoading } = useApps([]);
  const { data: linkedAccounts, isPending: linkedAccountsLoading } =
    useLinkedAccounts();

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      app_name: "",
      linked_account_owner_id: "",
      trigger_type: "",
      trigger_name: "",
      description: "",
      config: {},
    },
  });

  const selectedAppName = form.watch("app_name");
  const selectedTriggerType = form.watch("trigger_type");

  // Fetch available trigger types for the selected app
  const { data: availableTriggers = [], isPending: triggerTypesLoading } =
    useAvailableTriggerTypes(selectedAppName);

  const filteredLinkedAccounts = linkedAccounts?.filter(
    (la) => la.app_name === selectedAppName,
  );

  const handleSubmit = async (values: FormValues) => {
    try {
      await createTrigger({
        app_name: values.app_name,
        linked_account_owner_id: values.linked_account_owner_id,
        trigger_name: values.trigger_name,
        trigger_type: values.trigger_type,
        description: values.description || `Trigger for ${values.trigger_type}`,
        config: values.config || {},
        status: "active",
      });

      toast.success("Trigger created", {
        description:
          "Your trigger has been successfully created and is now active.",
      });

      form.reset();
      setStep(1);
      onOpenChange(false);
    } catch (error) {
      toast.error("Failed to create trigger", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  };

  const handleNext = async () => {
    const fieldsToValidate =
      step === 1
        ? ["app_name", "linked_account_owner_id"]
        : step === 2
          ? ["trigger_type"]
          : [];

    const isValid = await form.trigger(fieldsToValidate as any);
    if (isValid) {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    setStep(step - 1);
  };

  const handleClose = () => {
    form.reset();
    setStep(1);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>Create New Trigger</DialogTitle>
          <DialogDescription>
            {step === 1 && "Select an app and linked account"}
            {step === 2 && "Choose the type of event to trigger on"}
            {step === 3 && "Configure your trigger details"}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            {/* Step 1: App & Account Selection */}
            {step === 1 && (
              <>
                <FormField
                  control={form.control}
                  name="app_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>App</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                        disabled={appsLoading}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select an app" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {apps
                            ?.filter((app) =>
                              [
                                "HUBSPOT",
                                "SHOPIFY",
                                "SLACK",
                                "GITHUB",
                                "GOOGLE_CALENDAR",
                                "MICROSOFT_CALENDAR",
                                "GMAIL",
                                "NOTION",
                              ].includes(app.name),
                            )
                            .map((app) => (
                              <SelectItem key={app.name} value={app.name}>
                                <div className="flex items-center gap-2">
                                  <span>{app.display_name}</span>
                                  <Badge variant="outline" className="text-xs">
                                    {app.category}
                                  </Badge>
                                </div>
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="linked_account_owner_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Linked Account</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                        disabled={!selectedAppName || linkedAccountsLoading}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a linked account" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {filteredLinkedAccounts?.map((account) => (
                            <SelectItem
                              key={account.id}
                              value={account.linked_account_owner_id}
                            >
                              {account.linked_account_owner_id}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        {!selectedAppName
                          ? "Select an app first"
                          : filteredLinkedAccounts?.length === 0
                            ? "No linked accounts found for this app"
                            : "Choose which account to use for this trigger"}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </>
            )}

            {/* Step 2: Trigger Type Selection */}
            {step === 2 && (
              <FormField
                control={form.control}
                name="trigger_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Trigger Type</FormLabel>
                    {triggerTypesLoading ? (
                      <div className="flex items-center justify-center p-8">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        <span className="ml-2 text-sm text-muted-foreground">
                          Loading available triggers...
                        </span>
                      </div>
                    ) : availableTriggers.length === 0 ? (
                      <div className="text-center p-8 border rounded-lg bg-muted/50">
                        <p className="text-sm text-muted-foreground">
                          No trigger types available for this app
                        </p>
                      </div>
                    ) : (
                      <div className="grid gap-3">
                        {availableTriggers.map((trigger) => (
                          <div
                            key={trigger.value}
                            className={`border rounded-lg p-4 cursor-pointer transition-colors ${
                              field.value === trigger.value
                                ? "border-primary bg-primary/5"
                                : "border-border hover:border-primary/50"
                            }`}
                            onClick={() => field.onChange(trigger.value)}
                          >
                            <div className="flex items-start justify-between">
                              <div>
                                <div className="font-medium">{trigger.label}</div>
                                <div className="text-sm text-muted-foreground mt-1">
                                  {trigger.description}
                                </div>
                              </div>
                              {field.value === trigger.value && (
                                <Badge>Selected</Badge>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/* Step 3: Configuration */}
            {step === 3 && (
              <>
                <FormField
                  control={form.control}
                  name="trigger_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Trigger Name</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g., New Orders Notification"
                          {...field}
                          disabled={isPending}
                        />
                      </FormControl>
                      <FormDescription>
                        A friendly name to identify this trigger
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Description (Optional)</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Describe what this trigger does..."
                          {...field}
                          disabled={isPending}
                          rows={3}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="rounded-lg border bg-muted/50 p-4">
                  <h4 className="text-sm font-medium mb-2">Summary</h4>
                  <div className="space-y-1 text-sm">
                    <div>
                      <span className="text-muted-foreground">App:</span>{" "}
                      <Badge variant="outline">{selectedAppName}</Badge>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Event:</span>{" "}
                      <code className="text-xs bg-background px-2 py-0.5 rounded">
                        {selectedTriggerType}
                      </code>
                    </div>
                  </div>
                </div>
              </>
            )}

            <DialogFooter className="flex justify-between">
              <div>
                {step > 1 && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleBack}
                    disabled={isPending}
                  >
                    <ChevronLeft className="mr-2 h-4 w-4" />
                    Back
                  </Button>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleClose}
                  disabled={isPending}
                >
                  Cancel
                </Button>
                {step < 3 ? (
                  <Button type="button" onClick={handleNext}>
                    Next
                    <ChevronRight className="ml-2 h-4 w-4" />
                  </Button>
                ) : (
                  <Button type="submit" disabled={isPending}>
                    {isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      "Create Trigger"
                    )}
                  </Button>
                )}
              </div>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
